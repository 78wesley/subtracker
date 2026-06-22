"""
cost_utils.py — Billing frequency helpers, cost normalisation, next-payment dates.

Frequency model
---------------
A subscription's cadence is described by three fields:
    frequency  — one of FREQUENCIES
    interval   — integer N (only meaningful for "custom"; named presets imply 1)
    base_unit  — for "custom" only: the unit the interval counts (BASE_UNITS)

Named presets (daily/weekly/monthly/quarterly/yearly) always mean "every 1 unit".
"custom" means "every <interval> <base_unit>" — e.g. every 6 months, every 2 weeks.
`resolve()` collapses the triple to an (effective_unit, n) pair that the math uses.
"""

import calendar
from datetime import date, timedelta

# ── Frequency model ──────────────────────────────────────────────────────────

FREQUENCIES = ["daily", "weekly", "monthly", "quarterly", "yearly", "custom"]
BASE_UNITS  = ["daily", "weekly", "monthly", "yearly"]

DAYS_PER_UNIT = {
    "daily":     1,
    "weekly":    7,
    "monthly":   30.4375,
    "quarterly": 91.3125,
    "yearly":    365.25,
}

# Output periods used by the cost-breakdown cards (NOT input frequencies).
PERIOD_DIVISORS = {
    "daily":     365.25,
    "weekly":    52.18,
    "monthly":   12,
    "quarterly": 4,
    "yearly":    1,
}

_UNIT_NOUN = {"daily": "day", "weekly": "week", "monthly": "month", "yearly": "year"}


def resolve(frequency: str, interval: int = 1, base_unit: str | None = None) -> tuple:
    """Collapse (frequency, interval, base_unit) to an (effective_unit, n) pair."""
    if frequency == "custom":
        unit = base_unit if base_unit in BASE_UNITS else "monthly"
        return unit, max(1, int(interval or 1))
    if frequency not in DAYS_PER_UNIT:
        frequency = "monthly"
    return frequency, 1


def normalise_cadence(frequency: str, interval=1, base_unit: str | None = None) -> tuple:
    """Clean a submitted/imported (frequency, interval, base_unit) triple for storage.

    A named preset always means "every 1 unit" with no base_unit. "custom" keeps a
    positive-integer interval and a valid base_unit (defaulting to monthly). Tolerates
    a non-integer `interval` (e.g. a string from an imported CSV). Returns the cleaned
    (frequency, interval, base_unit).
    """
    frequency = frequency if frequency in FREQUENCIES else "monthly"
    if frequency != "custom":
        return frequency, 1, None
    base_unit = base_unit if base_unit in BASE_UNITS else "monthly"
    try:
        interval = max(1, int(interval))
    except (TypeError, ValueError):
        interval = 1
    return frequency, interval, base_unit


# ── Cost normalisation ───────────────────────────────────────────────────────

def get_annual_cost(amount: float, frequency: str, interval: int = 1,
                    base_unit: str | None = None) -> float:
    unit, n = resolve(frequency, interval, base_unit)
    days_between = DAYS_PER_UNIT[unit] * n
    return round(amount * (365.25 / days_between), 2)


def get_period_cost(amount: float, frequency: str, interval: int,
                    base_unit: str | None, period: str) -> float:
    return round(get_annual_cost(amount, frequency, interval, base_unit)
                 / PERIOD_DIVISORS[period], 2)


def frequency_label(frequency: str, interval: int = 1, base_unit: str | None = None) -> str:
    named = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
             "quarterly": "Quarterly", "yearly": "Yearly"}
    if frequency != "custom":
        return named.get(frequency, (frequency or "").capitalize())
    unit = base_unit if base_unit in _UNIT_NOUN else "monthly"
    n = max(1, int(interval or 1))
    noun = _UNIT_NOUN[unit]
    return f"Every {noun}" if n == 1 else f"Every {n} {noun}s"


# ── Interval arithmetic (no external deps) ───────────────────────────────────

def _advance(d: date, unit: str, n: int) -> date:
    """Advance a date by n billing units using only stdlib."""
    if unit == "daily":
        return d + timedelta(days=n)
    if unit == "weekly":
        return d + timedelta(weeks=n)
    if unit in ("monthly", "quarterly"):
        months = (1 if unit == "monthly" else 3) * n
        m = d.month - 1 + months
        year = d.year + m // 12
        month = m % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    if unit == "yearly":
        year = d.year + n
        day = min(d.day, calendar.monthrange(year, d.month)[1])
        return date(year, d.month, day)
    raise ValueError(f"Unknown unit: {unit}")


def next_payment_date(start_date_str: str, frequency: str, interval: int,
                      base_unit: str | None = None, reference: date | None = None) -> date:
    """Return the next payment date >= reference (defaults to today)."""
    ref = reference or date.today()
    unit, n = resolve(frequency, interval, base_unit)
    d = date.fromisoformat(start_date_str)
    if d >= ref:
        return d
    while d < ref:
        d = _advance(d, unit, n)
    return d


def upcoming_payments_for_periods(sub: dict, periods: list, count: int = 6,
                                  reference: date | None = None) -> list:
    """
    Return up to `count` upcoming [{date, amount}] payments at/after `reference`,
    walking each period's cadence (anchored at its start) and clamped to its end.
    """
    ref = reference or date.today()
    out: list = []
    freq, interval, base_unit = sub["frequency"], sub.get("interval") or 1, sub.get("base_unit")
    for p in sorted(periods, key=lambda x: x["start_date"]):
        pe = date.fromisoformat(p["end_date"]) if p.get("end_date") else None
        anchor = max(ref, date.fromisoformat(p["start_date"]))
        d = next_payment_date(p["start_date"], freq, interval, base_unit, anchor)
        while (pe is None or d <= pe) and len(out) < count:
            out.append({"date": d, "amount": p["amount"]})
            d = next_payment_date(p["start_date"], freq, interval, base_unit,
                                  d + timedelta(days=1))
        if len(out) >= count:
            break
    return out


# ── Range-aware cost (sums per-period prorated cost over a window) ────────────

def range_cost(sub: dict, periods: list, range_start: date, range_end: date) -> float:
    """
    True cost of a subscription over an inclusive [range_start, range_end] window:
    each period contributes its prorated cost across the days it overlaps the window.
    periods: list of dicts with 'amount', 'start_date', and nullable 'end_date'.
    """
    total = 0.0
    for p in periods:
        ps = date.fromisoformat(p["start_date"])
        pe = date.fromisoformat(p["end_date"]) if p.get("end_date") else range_end
        window_start = max(range_start, ps)
        window_end   = min(range_end,   pe)
        if window_start > window_end:
            continue
        days = (window_end - window_start).days + 1
        daily = get_period_cost(p["amount"], sub["frequency"],
                                sub.get("interval") or 1, sub.get("base_unit"), "daily")
        total += daily * days
    return round(total, 2)


def year_cost(sub: dict, periods: list, year: int) -> float:
    """True cost of a subscription across a calendar year, summing its periods."""
    return range_cost(sub, periods, date(year, 1, 1), date(year, 12, 31))


def monthly_costs_for_year(sub: dict, periods: list, year: int) -> list:
    """Return a 12-element list of this subscription's cost per month for `year`."""
    out = []
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        out.append(range_cost(
            sub, periods, date(year, month, 1), date(year, month, last_day)))
    return out
