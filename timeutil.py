"""
timeutil.py — Central date/time provider for the whole application.

To debug with a fixed date, set DEBUG_DATE in your environment:
    DEBUG_DATE=2025-01-15 python main.py

Or call set_debug_date() at runtime via the /debug/set-date admin route.
"""

import os
from datetime import date, datetime

# Module-level override; set this to a date string "YYYY-MM-DD" to freeze time.
_debug_date: str | None = os.environ.get("DEBUG_DATE")


def set_debug_date(d: str | None) -> None:
    """Set a fixed date for debugging (None to restore real clock)."""
    global _debug_date
    _debug_date = d


def today() -> date:
    """Return today's date, respecting any debug override."""
    if _debug_date:
        return date.fromisoformat(_debug_date)
    return date.today()


def today_iso() -> str:
    """Return today as 'YYYY-MM-DD'."""
    return today().isoformat()


def now_iso() -> str:
    """Return current datetime as ISO string, using debug date if set."""
    if _debug_date:
        d = date.fromisoformat(_debug_date)
        return datetime(d.year, d.month, d.day, 12, 0, 0).isoformat()
    return datetime.now().isoformat()


def get_debug_date() -> str | None:
    """Return the currently active debug date string, or None."""
    return _debug_date
