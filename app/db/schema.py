"""
schema.py — Idempotent SQLite schema initialisation + RBAC seed.

Create-if-absent for every table, add-column-if-absent for additive changes, so
init_db() is safe to call on every boot. Multi-tenant: subscriptions are owned by
a team; users carry a global role; teams/memberships and a DB-driven role matrix
back the RBAC system. audit_log is intentionally FK-free and denormalised so
entries survive permanent deletion.
"""

from datetime import date, timedelta

from app import timeutil
from app.db.connection import get_db
from app.db.seed import seed_rbac


def _ensure_columns(db, table: str, cols: dict) -> None:
    existing = db[table].columns_dict
    for name, typ in cols.items():
        if name not in existing:
            db[table].add_column(name, typ)


def _migrate_to_periods(db) -> None:
    """
    One-shot backfill of subscription_periods from the legacy single-window +
    price_history model, then drop the legacy columns/table. Detected by the
    presence of the legacy `start_date` column on subscriptions; once dropped this
    is a no-op, so it is safe to call on every boot.
    """
    if "start_date" not in db["subscriptions"].columns_dict:
        return  # already migrated (or a fresh new-schema DB)

    today = timeutil.today_iso()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()

    for sub in db["subscriptions"].rows:
        start = sub.get("start_date") or (sub.get("created_at") or today)[:10]
        end = sub.get("end_date") or None
        base_amount = sub.get("amount") or 0.0

        history = sorted(
            db["subscription_price_history"].rows_where(
                "subscription_id = ?", [sub["id"]]),
            key=lambda h: (h["valid_from"], h["id"]))

        def price_at(d: str, base_amount=base_amount, history=history) -> float:
            active = base_amount
            for h in history:
                if h["valid_from"] <= d:
                    active = h["amount"]
            return active

        # Breakpoints strictly inside the active window become new period starts.
        bps = sorted({h["valid_from"] for h in history
                      if h["valid_from"] > start and (end is None or h["valid_from"] <= end)})
        seg_starts = [start] + bps

        periods: list[dict] = []
        for i, ss in enumerate(seg_starts):
            se = (date.fromisoformat(seg_starts[i + 1]) - timedelta(days=1)).isoformat() \
                if i + 1 < len(seg_starts) else end
            periods.append({"start_date": ss, "end_date": se, "amount": price_at(ss)})

        # Legacy is_active=0 means "disabled regardless of dates": ensure the final
        # period reads inactive today by capping its open/future end at yesterday.
        if not sub.get("is_active") and periods:
            last = periods[-1]
            if last["end_date"] is None or last["end_date"] >= today:
                last["end_date"] = max(yesterday, last["start_date"])

        now = timeutil.now_iso()
        for p in periods:
            db["subscription_periods"].insert({
                "subscription_id": sub["id"], "amount": p["amount"],
                "start_date": p["start_date"], "end_date": p["end_date"],
                "created_at": now, "created_by": sub.get("created_by"),
            })

    db["subscriptions"].transform(drop=["start_date", "end_date", "amount", "is_active"])
    if "subscription_price_history" in db.table_names():
        db["subscription_price_history"].drop()


def init_db():
    db = get_db()
    tables = db.table_names()

    if "users" not in tables:
        db["users"].create({
            "id": int, "username": str, "password_hash": str, "global_role": str,
            "created_at": str, "deleted_at": str, "deleted_by": int,
        }, pk="id", not_null={"username", "password_hash"})
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_live "
                   "ON users(username) WHERE deleted_at IS NULL")
    else:
        _ensure_columns(db, "users", {"global_role": str})

    if "teams" not in tables:
        db["teams"].create({
            "id": int, "name": str, "slug": str, "description": str,
            "created_at": str, "created_by": int,
            "deleted_at": str, "deleted_by": int,
        }, pk="id")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_teams_slug_live "
                   "ON teams(slug) WHERE deleted_at IS NULL")

    if "team_members" not in tables:
        db["team_members"].create({
            "id": int, "team_id": int, "user_id": int, "team_role": str,
            "created_at": str, "created_by": int,
            "deleted_at": str, "deleted_by": int,
        }, pk="id", foreign_keys=[
            ("team_id", "teams", "id"), ("user_id", "users", "id"),
        ])
        # One live membership per (team, user).
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_live "
                   "ON team_members(team_id, user_id) WHERE deleted_at IS NULL")
        db["team_members"].create_index(["team_id"])
        db["team_members"].create_index(["user_id"])

    if "roles" not in tables:
        db["roles"].create({
            "name": str, "scope": str, "label": str, "is_system": int, "rank": int,
        }, pk="name")

    if "permissions" not in tables:
        db["permissions"].create({"name": str, "label": str, "category": str}, pk="name")

    if "role_permissions" not in tables:
        db["role_permissions"].create(
            {"role_name": str, "permission_name": str},
            pk=("role_name", "permission_name"))
        db["role_permissions"].create_index(["role_name"])

    if "subscriptions" not in tables:
        # Cadence/identity metadata only. Dated active windows + prices live in
        # subscription_periods (a sub can have several non-overlapping periods).
        db["subscriptions"].create({
            "id": int, "team_id": int, "created_by": int, "name": str,
            "currency": str, "category": str, "notes": str,
            "frequency": str, "interval": int, "base_unit": str,
            "created_at": str, "updated_at": str,
            "deleted_at": str, "deleted_by": int,
        }, pk="id", foreign_keys=[
            ("team_id", "teams", "id"), ("created_by", "users", "id"),
        ])
        db["subscriptions"].create_index(["team_id", "deleted_at"])

    if "subscription_periods" not in tables:
        db["subscription_periods"].create({
            "id": int, "subscription_id": int, "amount": float,
            "start_date": str, "end_date": str,
            "created_at": str, "created_by": int,
        }, pk="id", foreign_keys=[
            ("subscription_id", "subscriptions", "id"),
            ("created_by", "users", "id"),
        ], not_null={"start_date", "amount"})
        db["subscription_periods"].create_index(["subscription_id"])

    _migrate_to_periods(db)

    if "audit_log" not in tables:
        # No foreign keys: audit must outlive the entities it references.
        db["audit_log"].create({
            "id": int,
            "actor_user_id": int, "actor_name": str, "actor_global_role": str,
            "team_id": int, "team_name": str,
            "action": str, "entity_type": str, "entity_id": int, "entity_name": str,
            "old_values": str, "new_values": str,
            "description": str, "timestamp": str,
        }, pk="id")
        db["audit_log"].create_index(["entity_type", "entity_id"])
        db["audit_log"].create_index(["actor_user_id"])
        db["audit_log"].create_index(["team_id"])

    seed_rbac(db)
    return db


def has_any_users(db) -> bool:
    """True if at least one live (non-deleted) user exists."""
    return next(db.query(
        "SELECT 1 FROM users WHERE deleted_at IS NULL LIMIT 1"), None) is not None
