"""
subscriptions.py — Team-scoped subscription and period queries.

The scope helper is the single choke point: every subscription read is filtered by
the caller's active team (or all teams for a super_admin in view-all mode) AND by
soft-delete state. There is no public way to read subscriptions by raw user_id, so
cross-team leakage and deleted-row leakage are structurally hard to introduce.

A subscription owns multiple non-overlapping periods (subscription_periods), each
with its own start/end dates and amount. "Active" and "current price" are derived
from these periods relative to a reference date — there is no stored is_active flag.
"""

import math
from datetime import date, timedelta

from app import timeutil
from app.db.connection import rows_as_dicts
from app.permissions import Perm


def _team_clause(ctx) -> tuple:
    """Return (sql_fragment, params) restricting rows to the caller's team(s)."""
    if ctx.view_all and ctx.is_super:
        return "1=1", []                         # all teams
    # active_team_id None (teamless user) -> impossible team id -> no rows
    return "team_id = ?", [ctx.active_team_id if ctx.active_team_id is not None else -1]


# SQL fragment: true when subscription `id` has a period covering :today.
_ACTIVE_EXISTS = (
    "EXISTS (SELECT 1 FROM subscription_periods p WHERE p.subscription_id = subscriptions.id "
    "AND p.start_date <= ? AND (p.end_date IS NULL OR p.end_date >= ?))"
)


def get_subscription(db, ctx, sub_id: int, include_deleted: bool = False):
    tc, tp = _team_clause(ctx)
    where = f"id = ? AND {tc}"
    if not (include_deleted and ctx.can(Perm.RECORDS_VIEW_DELETED)):
        where += " AND deleted_at IS NULL"
    rows = list(db["subscriptions"].rows_where(where, [sub_id] + tp))
    return rows[0] if rows else None


def get_all_subscriptions(db, ctx, filter_active: str | None = None, search: str | None = None,
                          category: str | None = None, only_deleted: bool = False) -> list:
    tc, tp = _team_clause(ctx)
    where, params = [tc], list(tp)
    if only_deleted and ctx.can(Perm.RECORDS_VIEW_DELETED):
        where.append("deleted_at IS NOT NULL")
    else:
        where.append("deleted_at IS NULL")
    today = timeutil.today_iso()
    if filter_active == "active":
        where.append(_ACTIVE_EXISTS)
        params += [today, today]
    elif filter_active == "inactive":
        where.append("NOT " + _ACTIVE_EXISTS)
        params += [today, today]
    if search:
        where.append("name LIKE ?")
        params.append(f"%{search}%")
    if category:
        where.append("COALESCE(NULLIF(TRIM(category), ''), 'Uncategorized') = ?")
        params.append(category)
    query = "SELECT * FROM subscriptions WHERE " + " AND ".join(where) + " ORDER BY name ASC"
    return rows_as_dicts(db, query, params)


def get_active_subscriptions(db, ctx) -> list:
    tc, tp = _team_clause(ctx)
    today = timeutil.today_iso()
    return rows_as_dicts(db,
        f"SELECT * FROM subscriptions WHERE {tc} AND deleted_at IS NULL "
        f"AND {_ACTIVE_EXISTS}",
        list(tp) + [today, today])


def get_categories(db, ctx) -> list:
    tc, tp = _team_clause(ctx)
    rows = rows_as_dicts(db,
        f"SELECT DISTINCT TRIM(category) AS c FROM subscriptions WHERE {tc} "
        "AND deleted_at IS NULL AND category IS NOT NULL AND TRIM(category) != '' "
        "ORDER BY c COLLATE NOCASE ASC", list(tp))
    return [r["c"] for r in rows]


# ── Periods (scoped via the owning subscription at the route layer) ───────────

def get_periods(db, subscription_id: int) -> list:
    """All periods for one subscription, earliest first."""
    return rows_as_dicts(db,
        "SELECT sp.id, sp.subscription_id, sp.amount, sp.start_date, sp.end_date, "
        "       sp.created_at, sp.created_by, u.username "
        "FROM subscription_periods sp "
        "LEFT JOIN users u ON u.id = sp.created_by "
        "WHERE sp.subscription_id = ? ORDER BY sp.start_date ASC, sp.id ASC",
        [subscription_id])


def get_periods_map(db, subscription_ids: list) -> dict:
    """{subscription_id: [periods]} for many subscriptions in one query (avoids N+1)."""
    out: dict[int, list] = {sid: [] for sid in subscription_ids}
    if not subscription_ids:
        return out
    placeholders = ",".join("?" * len(subscription_ids))
    rows = rows_as_dicts(db,
        f"SELECT id, subscription_id, amount, start_date, end_date "
        f"FROM subscription_periods WHERE subscription_id IN ({placeholders}) "
        "ORDER BY start_date ASC, id ASC", list(subscription_ids))
    for r in rows:
        out.setdefault(r["subscription_id"], []).append(r)
    return out


def is_active_on(periods: list, reference_date: str | None = None) -> bool:
    """True if any period covers the reference date (defaults to today)."""
    ref = reference_date or timeutil.today_iso()
    return any(p["start_date"] <= ref and (p["end_date"] is None or p["end_date"] >= ref)
               for p in periods)


def upcoming_price_change(periods: list, reference_date: str | None = None):
    """
    The next scheduled price change relative to the reference date (default today):
    the earliest future period whose amount differs from the current price.
    Returns {start_date, amount, current} or None when no change is queued.
    """
    ref = reference_date or timeutil.today_iso()
    cur = current_price(periods, ref)
    if cur is None:
        return None
    for p in sorted((p for p in periods if p["start_date"] > ref),
                    key=lambda p: p["start_date"]):
        if p["amount"] != cur:
            return {"start_date": p["start_date"], "amount": p["amount"], "current": cur}
    return None


def current_price(periods: list, reference_date: str | None = None):
    """
    Price in effect at the reference date: the covering period's amount, else the
    most recent already-started period, else the earliest period. None if no periods.
    """
    if not periods:
        return None
    ref = reference_date or timeutil.today_iso()
    covering = [p for p in periods
                if p["start_date"] <= ref and (p["end_date"] is None or p["end_date"] >= ref)]
    if covering:
        return covering[-1]["amount"]
    started = [p for p in periods if p["start_date"] <= ref]
    if started:
        return max(started, key=lambda p: p["start_date"])["amount"]
    return min(periods, key=lambda p: p["start_date"])["amount"]


def validate_periods(periods: list) -> str:
    """
    Return an error message if any two periods overlap or a period is malformed,
    else "". `periods` is a list of dicts with start_date and (nullable) end_date.
    """
    for p in periods:
        amt = p.get("amount")
        try:
            amt_ok = amt is not None and math.isfinite(float(amt)) and float(amt) >= 0
        except (TypeError, ValueError):
            amt_ok = False
        if not amt_ok:
            return "Amount must be a number that is zero or more."
        sd = p.get("start_date")
        if not sd:
            return "Every period needs a start date."
        if not timeutil.valid_iso_date(sd):
            return f"Invalid start date '{sd}' — use the YYYY-MM-DD format."
        ed = p.get("end_date")
        if ed and not timeutil.valid_iso_date(ed):
            return f"Invalid end date '{ed}' — use the YYYY-MM-DD format."
        if ed and ed < sd:
            return f"Period starting {sd} ends before it begins."
    ordered = sorted(periods, key=lambda p: p["start_date"])
    for prev, nxt in zip(ordered, ordered[1:]):
        # An open-ended earlier period swallows everything after it.
        if prev["end_date"] is None or prev["end_date"] >= nxt["start_date"]:
            return (f"Periods overlap: one running from {prev['start_date']} "
                    f"clashes with the period starting {nxt['start_date']}.")
    return ""


def add_period(db, subscription_id: int, amount: float, start_date: str,
               end_date: str, created_by: int) -> tuple:
    """
    Insert a period, validating against existing ones. Returns (error, note):
    error is "" on success, else a message. As a convenience, an existing
    open-ended period that starts before the new one is auto-closed the day before
    it begins — a later period is the "further notice" that ends the open run, so
    this models a price change. `note` describes any such auto-close (else "").
    Genuine overlaps with bounded periods are still rejected.
    """
    # Validate date formats up front so the date.fromisoformat below can't throw
    # (a malformed imported/posted date would otherwise crash the request).
    if not timeutil.valid_iso_date(start_date):
        return f"Invalid start date '{start_date}' — use the YYYY-MM-DD format.", ""
    if end_date and not timeutil.valid_iso_date(end_date):
        return f"Invalid end date '{end_date}' — use the YYYY-MM-DD format.", ""

    candidate = {"start_date": start_date, "end_date": end_date or None, "amount": amount}
    existing = get_periods(db, subscription_id)

    # An open-ended period starting earlier must yield to the new one.
    day_before = (date.fromisoformat(start_date) - timedelta(days=1)).isoformat()
    to_close = [p for p in existing
                if p["end_date"] is None and p["start_date"] < start_date]

    validation_set = [
        {**p, "end_date": day_before} if p in to_close else p for p in existing
    ] + [candidate]
    err = validate_periods(validation_set)
    if err:
        return err, ""

    for p in to_close:
        db["subscription_periods"].update(p["id"], {"end_date": day_before})
    db["subscription_periods"].insert({
        "subscription_id": subscription_id, "amount": amount,
        "start_date": start_date, "end_date": end_date or None,
        "created_at": timeutil.now_iso(), "created_by": created_by,
    })
    note = (f"Closed the previous open-ended period on {day_before}." if to_close else "")
    return "", note


def update_period(db, subscription_id: int, period_id: int, amount: float,
                  start_date: str, end_date: str) -> str:
    """Update a period, re-validating against the others. Returns "" or an error."""
    candidate = {"start_date": start_date, "end_date": end_date or None, "amount": amount}
    others = [p for p in get_periods(db, subscription_id) if p["id"] != period_id]
    err = validate_periods(others + [candidate])
    if err:
        return err
    db["subscription_periods"].update(period_id, {
        "amount": amount, "start_date": start_date, "end_date": end_date or None})
    return ""


def delete_period(db, period_id: int, subscription_id: int) -> bool:
    rows = list(db["subscription_periods"].rows_where(
        "id = ? AND subscription_id = ?", [period_id, subscription_id]))
    if not rows:
        return False
    db["subscription_periods"].delete(period_id)
    return True


# ── Restore / permanent delete (admin lifecycle) ─────────────────────────────

def restore_subscription(db, sub_id: int) -> None:
    db["subscriptions"].update(sub_id, {
        "deleted_at": None, "deleted_by": None, "updated_at": timeutil.now_iso()})


def purge_subscription(db, sub_id: int) -> None:
    """Hard-delete a subscription and its periods. Audit BEFORE calling this."""
    db["subscription_periods"].delete_where("subscription_id = ?", [sub_id])
    db["subscriptions"].delete(sub_id)
