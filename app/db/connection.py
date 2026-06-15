"""
connection.py — SQLite connection + low-level row helpers.
"""

import sqlite_utils

from app.config import DB_PATH


def get_db() -> sqlite_utils.Database:
    db = sqlite_utils.Database(DB_PATH)
    # Wait (up to 5s) for a competing writer instead of failing immediately with
    # "database is locked" — fresh connection per call, so set it each time.
    db.execute("PRAGMA busy_timeout=5000")
    return db


def rows_as_dicts(db, query: str, params: list) -> list:
    """Execute a query and return rows as dicts using column names from cursor."""
    cur = db.execute(query, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(db, table: str, where: str, params: list):
    rows = list(db[table].rows_where(where, params))
    return rows[0] if rows else None
