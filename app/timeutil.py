"""
timeutil.py — Central date/time provider for the whole application.

All code reads the current date/time through these helpers (never `date.today()`
directly) so behaviour is consistent and trivially mockable in tests.
"""

from datetime import date, datetime


def today() -> date:
    """Return today's date."""
    return date.today()


def today_iso() -> str:
    """Return today as 'YYYY-MM-DD'."""
    return today().isoformat()


def now_iso() -> str:
    """Return the current datetime as an ISO string."""
    return datetime.now().isoformat()


def valid_iso_date(s: str) -> bool:
    """True if `s` is a parseable 'YYYY-MM-DD' date string."""
    if not isinstance(s, str):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False
