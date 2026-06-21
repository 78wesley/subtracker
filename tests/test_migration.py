"""
The one-shot legacy→periods migration in schema._migrate_to_periods.

We hand-build a database in the OLD shape (single window + price_history) and run
init_db(), which detects the legacy `start_date` column and migrates it.
"""

import sqlite_utils

from app.db.schema import init_db


def _legacy_db(path):
    """Create a database with the pre-periods subscriptions shape."""
    db = sqlite_utils.Database(path)
    db["subscriptions"].create({
        "id": int, "team_id": int, "created_by": int, "name": str,
        "currency": str, "category": str, "notes": str,
        "frequency": str, "interval": int, "base_unit": str,
        "created_at": str, "updated_at": str, "deleted_at": str, "deleted_by": int,
        "start_date": str, "end_date": str, "amount": float, "is_active": int,
    }, pk="id")
    db["subscription_price_history"].create({
        "id": int, "subscription_id": int, "amount": float, "valid_from": str,
    }, pk="id")
    return db


def test_price_change_splits_into_two_periods(db_path):
    db = _legacy_db(db_path)
    db["subscriptions"].insert({
        "id": 1, "name": "Netflix", "frequency": "monthly", "interval": 1,
        "start_date": "2024-01-01", "end_date": None, "amount": 10.0, "is_active": 1,
    })
    db["subscription_price_history"].insert({
        "id": 1, "subscription_id": 1, "amount": 15.0, "valid_from": "2024-06-01",
    })

    init_db()  # triggers _migrate_to_periods on the legacy db

    db = sqlite_utils.Database(db_path)
    periods = sorted(db["subscription_periods"].rows, key=lambda p: p["start_date"])
    assert len(periods) == 2
    assert (periods[0]["start_date"], periods[0]["end_date"], periods[0]["amount"]) \
        == ("2024-01-01", "2024-05-31", 10.0)
    assert (periods[1]["start_date"], periods[1]["end_date"], periods[1]["amount"]) \
        == ("2024-06-01", None, 15.0)

    # Legacy columns/table are gone afterwards.
    assert "start_date" not in db["subscriptions"].columns_dict
    assert "subscription_price_history" not in db.table_names()


def test_inactive_legacy_sub_caps_final_period(db_path):
    db = _legacy_db(db_path)
    db["subscriptions"].insert({
        "id": 1, "name": "Old", "frequency": "monthly", "interval": 1,
        "start_date": "2024-01-01", "end_date": None, "amount": 5.0, "is_active": 0,
    })

    init_db()

    db = sqlite_utils.Database(db_path)
    periods = list(db["subscription_periods"].rows)
    assert len(periods) == 1
    # is_active=0 → the open-ended final period must be closed (not left None).
    assert periods[0]["end_date"] is not None


def test_migration_is_noop_on_fresh_schema(db):
    # `db` fixture already ran init_db on a new-shape DB; running again is safe.
    init_db()
    assert "subscription_periods" in db.table_names()
    assert "start_date" not in db["subscriptions"].columns_dict
