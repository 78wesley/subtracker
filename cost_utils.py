"""
cost_utils.py — Billing frequency helpers, cost normalisation, next-payment dates.
"""

from datetime import date, timedelta


# ── Frequency helpers ──────────────────────────────────────────────────────────

REPEAT_UNITS = ["daily", "weekly", "monthly", "quarterly", "halfyear", "yearly"]

DAYS_PER_UNIT = {
    "daily":     1,
    "weekly":    7,
    "monthly":   30.4375,
    "quarterly": 91.3125,
    "halfyear":  182.625,
    "yearly":    365.25,
}

PERIOD_DIVISORS = {
    "daily":     365.25,
    "weekly":    52.18,
    "monthly":   12,
    "quarterly": 4,
    "yearly":    1,
}


def get_annual_cost(amount: float, repeat_unit: str, repeat_skip: int = 1) -> float:
    days_between = DAYS_PER_UNIT[repeat_unit] * repeat_skip
    return round(amount * (365.25 / days_between), 2)


def get_period_cost(amount: float, repeat_unit: str, repeat_skip: int, period: str) -> float:
    return round(get_annual_cost(amount, repeat_unit, repeat_skip) / PERIOD_DIVISORS[period], 2)


def frequency_label(repeat_unit: str, repeat_skip: int) -> str:
    singular = {
        "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
        "quarterly": "Quarterly", "halfyear": "Every 6 months", "yearly": "Yearly",
    }
    return singular.get(repeat_unit, repeat_unit) if repeat_skip == 1 else f"Every {repeat_skip} {repeat_unit}s"


# ── Interval arithmetic (no external deps) ────────────────────────────────────

def _add_interval(d: date, repeat_unit: str, repeat_skip: int) -> date:
    """Advance date by one billing interval using only stdlib."""
    n = repeat_skip
    if repeat_unit == "daily":
        return d + timedelta(days=n)
    if repeat_unit == "weekly":
        return d + timedelta(weeks=n)
    if repeat_unit in ("monthly", "quarterly", "halfyear"):
        months = {"monthly": 1, "quarterly": 3, "halfyear": 6}[repeat_unit] * n
        m = d.month - 1 + months
        year = d.year + m // 12
        month = m % 12 + 1
        import calendar
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    if repeat_unit == "yearly":
        import calendar
        year = d.year + n
        day = min(d.day, calendar.monthrange(year, d.month)[1])
        return date(year, d.month, day)
    raise ValueError(f"Unknown repeat_unit: {repeat_unit}")


def next_payment_date(start_date_str: str, repeat_unit: str, repeat_skip: int,
                      reference: date = None) -> date:
    """Return the next payment date >= reference (defaults to today)."""
    ref = reference or date.today()
    d = date.fromisoformat(start_date_str)
    if d >= ref:
        return d
    while d < ref:
        d = _add_interval(d, repeat_unit, repeat_skip)
    return d


def upcoming_payments(subs: list, price_fn, days: int = 30, reference: date = None) -> list:
    """
    Return [{sub, next_date, amount}] for subscriptions due within `days` of reference.
    price_fn(sub_id, fallback_amount) -> float
    """
    ref = reference or date.today()
    cutoff = ref + timedelta(days=days)
    results = []
    for s in subs:
        if not s.get("start_date"):
            continue
        nd = next_payment_date(s["start_date"], s["repeat_unit"], s["repeat_skip"] or 1, ref)
        if nd <= cutoff:
            results.append({"sub": s, "next_date": nd, "amount": price_fn(s["id"], s["amount"])})
    results.sort(key=lambda x: x["next_date"])
    return results


# ── Year-aware cost (respects price history mid-year changes) ─────────────────

def year_cost_with_price_history(sub: dict, price_history: list, year: int) -> float:
    """
    True cost of a subscription in a calendar year, honouring all price changes.
    price_history: list of dicts with 'amount' (float) and 'valid_from' (str YYYY-MM-DD).
    """
    year_start = date(year, 1, 1)
    year_end   = date(year, 12, 31)

    sub_start = date.fromisoformat(sub["start_date"]) if sub.get("start_date") else year_start
    sub_end   = date.fromisoformat(sub["end_date"])   if sub.get("end_date")   else year_end

    window_start = max(year_start, sub_start)
    window_end   = min(year_end,   sub_end)

    if window_start > window_end:
        return 0.0

    history_sorted = sorted(price_history, key=lambda h: h["valid_from"])

    def price_at(d: date) -> float:
        active = None
        for h in history_sorted:
            if date.fromisoformat(h["valid_from"]) <= d:
                active = h["amount"]
        return active if active is not None else sub["amount"]

    # Build breakpoints at every price-change boundary inside the window
    breakpoints = [window_start]
    for h in history_sorted:
        vf = date.fromisoformat(h["valid_from"])
        if window_start < vf <= window_end:
            breakpoints.append(vf)
    breakpoints.append(window_end + timedelta(days=1))

    total = 0.0
    for i in range(len(breakpoints) - 1):
        seg_start = breakpoints[i]
        seg_end   = breakpoints[i + 1] - timedelta(days=1)
        days_in_seg = (seg_end - seg_start).days + 1
        daily = get_period_cost(price_at(seg_start), sub["repeat_unit"], sub["repeat_skip"] or 1, "daily")
        total += daily * days_in_seg

    return round(total, 2)
