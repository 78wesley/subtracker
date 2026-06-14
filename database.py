"""
database.py — SQLite initialisation and all query helpers.
"""

import sqlite_utils
import json
from pathlib import Path

import timeutil

DB_PATH = Path(__file__).parent / "subscriptions.db"


# ── Connection ─────────────────────────────────────────────────────────────────

def get_db() -> sqlite_utils.Database:
    return sqlite_utils.Database(DB_PATH)


def init_db() -> sqlite_utils.Database:
    db = get_db()

    if "users" not in db.table_names():
        db["users"].create({
            "id": int, "username": str, "password_hash": str, "created_at": str,
        }, pk="id", not_null={"username", "password_hash"})
        db["users"].create_index(["username"], unique=True)

    if "subscriptions" not in db.table_names():
        db["subscriptions"].create({
            "id": int, "user_id": int, "name": str, "amount": float,
            "currency": str, "category": str, "start_date": str, "end_date": str,
            "notes": str, "repeat_unit": str, "repeat_skip": int, "is_active": int,
            "created_at": str, "updated_at": str,
        }, pk="id", foreign_keys=[("user_id", "users", "id")])
    elif "category" not in db["subscriptions"].columns_dict:
        # Migration: add category to pre-existing databases.
        db["subscriptions"].add_column("category", str)

    if "subscription_price_history" not in db.table_names():
        db["subscription_price_history"].create({
            "id": int, "subscription_id": int, "amount": float,
            "valid_from": str, "created_at": str, "created_by": int,
        }, pk="id", foreign_keys=[
            ("subscription_id", "subscriptions", "id"),
            ("created_by", "users", "id"),
        ])

    if "audit_log" not in db.table_names():
        db["audit_log"].create({
            "id": int, "user_id": int, "action": str, "entity_type": str,
            "entity_id": int, "old_values": str, "new_values": str,
            "description": str, "timestamp": str,
        }, pk="id", foreign_keys=[("user_id", "users", "id")])

    return db


# ── Generic helpers ────────────────────────────────────────────────────────────

def _rows_as_dicts(db, query: str, params: list) -> list:
    """Execute a query and return rows as dicts using column names from cursor."""
    cur = db.execute(query, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _one(db, table: str, where: str, params: list):
    rows = list(db[table].rows_where(where, params))
    return rows[0] if rows else None


# ── User queries ───────────────────────────────────────────────────────────────

def get_user_by_username(db, username: str):
    return _one(db, "users", "username = ?", [username])


def get_user_by_id(db, user_id: int):
    return _one(db, "users", "id = ?", [user_id])


def has_any_users(db) -> bool:
    return db["users"].count > 0


# ── Subscription queries ───────────────────────────────────────────────────────

def get_subscription(db, sub_id: int, user_id: int):
    return _one(db, "subscriptions", "id = ? AND user_id = ?", [sub_id, user_id])


def get_active_subscriptions(db, user_id: int) -> list:
    today = timeutil.today_iso()
    return _rows_as_dicts(db,
        "SELECT * FROM subscriptions WHERE user_id = ? AND is_active = 1 "
        "AND (end_date IS NULL OR end_date >= ?)",
        [user_id, today])


def get_all_subscriptions(db, user_id: int, filter_active: str = None,
                          search: str = None, category: str = None) -> list:
    query = "SELECT * FROM subscriptions WHERE user_id = ?"
    params = [user_id]
    if filter_active == "active":
        query += " AND is_active = 1"
    elif filter_active == "inactive":
        query += " AND is_active = 0"
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")
    if category:
        query += " AND COALESCE(NULLIF(TRIM(category), ''), 'Uncategorized') = ?"
        params.append(category)
    query += " ORDER BY name ASC"
    return _rows_as_dicts(db, query, params)


def get_categories(db, user_id: int) -> list:
    """Distinct non-empty category names for a user, alphabetically sorted."""
    rows = _rows_as_dicts(db,
        "SELECT DISTINCT TRIM(category) AS c FROM subscriptions "
        "WHERE user_id = ? AND category IS NOT NULL AND TRIM(category) != '' "
        "ORDER BY c COLLATE NOCASE ASC",
        [user_id])
    return [r["c"] for r in rows]


# ── Price history queries ──────────────────────────────────────────────────────

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
    return _rows_as_dicts(db,
        "SELECT sph.id, sph.subscription_id, sph.amount, sph.valid_from, "
        "       sph.created_at, sph.created_by, u.username "
        "FROM subscription_price_history sph "
        "LEFT JOIN users u ON u.id = sph.created_by "
        "WHERE sph.subscription_id = ? ORDER BY sph.valid_from ASC, sph.id ASC",
        [subscription_id])


def delete_price_history_entry(db, entry_id: int, subscription_id: int) -> bool:
    """Delete a single price-history row; returns True if it existed."""
    rows = list(db["subscription_price_history"].rows_where(
        "id = ? AND subscription_id = ?", [entry_id, subscription_id]))
    if not rows:
        return False
    db["subscription_price_history"].delete(entry_id)
    return True


# ── Audit queries ──────────────────────────────────────────────────────────────

def get_audit_for_entity(db, entity_id: int, entity_type: str) -> list:
    return _rows_as_dicts(db,
        "SELECT * FROM audit_log WHERE entity_id = ? AND entity_type = ? "
        "ORDER BY timestamp DESC",
        [entity_id, entity_type])


def get_audit_log(db, user_id: int, action_filter: str = None,
                  page: int = 1, per_page: int = 25) -> tuple:
    base = "SELECT * FROM audit_log WHERE user_id = ?"
    params = [user_id]
    if action_filter:
        base += " AND action = ?"
        params.append(action_filter)
    total = db.execute(f"SELECT COUNT(*) FROM ({base})", params).fetchone()[0]
    query = base + f" ORDER BY timestamp DESC LIMIT {per_page} OFFSET {(page-1)*per_page}"
    return _rows_as_dicts(db, query, params), total
