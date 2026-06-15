"""
subscriptions.py — Team-scoped subscription and price-history queries.

The scope helper is the single choke point: every subscription read is filtered by
the caller's active team (or all teams for a super_admin in view-all mode) AND by
soft-delete state. There is no public way to read subscriptions by raw user_id, so
cross-team leakage and deleted-row leakage are structurally hard to introduce.
"""

from app import timeutil
from app.db.connection import rows_as_dicts


def _team_clause(ctx) -> tuple:
    """Return (sql_fragment, params) restricting rows to the caller's team(s)."""
    if ctx.view_all and ctx.is_super:
        return "1=1", []                         # all teams
    # active_team_id None (teamless user) -> impossible team id -> no rows
    return "team_id = ?", [ctx.active_team_id if ctx.active_team_id is not None else -1]


def get_subscription(db, ctx, sub_id: int, include_deleted: bool = False):
    tc, tp = _team_clause(ctx)
    where = f"id = ? AND {tc}"
    if not (include_deleted and ctx.can("records.view_deleted")):
        where += " AND deleted_at IS NULL"
    rows = list(db["subscriptions"].rows_where(where, [sub_id] + tp))
    return rows[0] if rows else None


def get_all_subscriptions(db, ctx, filter_active: str = None, search: str = None,
                          category: str = None, only_deleted: bool = False) -> list:
    tc, tp = _team_clause(ctx)
    where, params = [tc], list(tp)
    if only_deleted and ctx.can("records.view_deleted"):
        where.append("deleted_at IS NOT NULL")
    else:
        where.append("deleted_at IS NULL")
    if filter_active == "active":
        where.append("is_active = 1")
    elif filter_active == "inactive":
        where.append("is_active = 0")
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
        "AND is_active = 1 AND (end_date IS NULL OR end_date >= ?)",
        list(tp) + [today])


def get_categories(db, ctx) -> list:
    tc, tp = _team_clause(ctx)
    rows = rows_as_dicts(db,
        f"SELECT DISTINCT TRIM(category) AS c FROM subscriptions WHERE {tc} "
        "AND deleted_at IS NULL AND category IS NOT NULL AND TRIM(category) != '' "
        "ORDER BY c COLLATE NOCASE ASC", list(tp))
    return [r["c"] for r in rows]


# ── Price history (scoped via the owning subscription at the route layer) ────

def get_active_price(db, subscription_id: int, amount_fallback: float,
                     reference_date: str = None) -> float:
    ref = reference_date or timeutil.today_iso()
    row = db.execute(
        "SELECT amount FROM subscription_price_history "
        "WHERE subscription_id = ? AND valid_from <= ? "
        "ORDER BY valid_from DESC, id DESC LIMIT 1",
        [subscription_id, ref]
    ).fetchone()
    return row[0] if row else amount_fallback


def get_price_history(db, subscription_id: int) -> list:
    return rows_as_dicts(db,
        "SELECT sph.id, sph.subscription_id, sph.amount, sph.valid_from, "
        "       sph.created_at, sph.created_by, u.username "
        "FROM subscription_price_history sph "
        "LEFT JOIN users u ON u.id = sph.created_by "
        "WHERE sph.subscription_id = ? ORDER BY sph.valid_from ASC, sph.id ASC",
        [subscription_id])


def delete_price_history_entry(db, entry_id: int, subscription_id: int) -> bool:
    rows = list(db["subscription_price_history"].rows_where(
        "id = ? AND subscription_id = ?", [entry_id, subscription_id]))
    if not rows:
        return False
    db["subscription_price_history"].delete(entry_id)
    return True


# ── Restore / permanent delete (admin lifecycle) ─────────────────────────────

def restore_subscription(db, sub_id: int) -> None:
    db["subscriptions"].update(sub_id, {
        "deleted_at": None, "deleted_by": None, "updated_at": timeutil.now_iso()})


def purge_subscription(db, sub_id: int) -> None:
    """Hard-delete a subscription and its price history. Audit BEFORE calling this."""
    db["subscription_price_history"].delete_where("subscription_id = ?", [sub_id])
    db["subscriptions"].delete(sub_id)
