"""Cost / cadence math — pure functions, no DB."""

from datetime import date

import pytest

from app import cost_utils as cu

# ── normalise_cadence ────────────────────────────────────────────────────────

def test_named_preset_drops_interval_and_base_unit():
    assert cu.normalise_cadence("monthly", 5, "weekly") == ("monthly", 1, None)


def test_unknown_frequency_falls_back_to_monthly():
    assert cu.normalise_cadence("fortnightly") == ("monthly", 1, None)


def test_custom_keeps_positive_interval_and_valid_unit():
    assert cu.normalise_cadence("custom", 6, "monthly") == ("custom", 6, "monthly")


def test_custom_tolerates_string_interval_from_csv():
    assert cu.normalise_cadence("custom", "3", "weekly") == ("custom", 3, "weekly")


def test_custom_coerces_bad_interval_to_one():
    assert cu.normalise_cadence("custom", "abc", "monthly") == ("custom", 1, "monthly")
    assert cu.normalise_cadence("custom", 0, "monthly") == ("custom", 1, "monthly")


# ── get_annual_cost ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("amount,freq,expected", [
    (10.0, "monthly", 120.0),
    (120.0, "yearly", 120.0),
    (7.0, "weekly", round(7 * 365.25 / 7, 2)),
    (1.0, "daily", 365.25),
])
def test_annual_cost_named(amount, freq, expected):
    assert cu.get_annual_cost(amount, freq) == expected


def test_annual_cost_custom_every_6_months():
    # every 6 months = twice a year
    assert cu.get_annual_cost(10.0, "custom", interval=6, base_unit="monthly") == 20.0


# ── frequency_label ──────────────────────────────────────────────────────────

def test_label_named():
    assert cu.frequency_label("monthly") == "Monthly"


def test_label_custom_singular_and_plural():
    assert cu.frequency_label("custom", 1, "monthly") == "Every month"
    assert cu.frequency_label("custom", 6, "monthly") == "Every 6 months"


# ── next_payment_date ────────────────────────────────────────────────────────

def test_next_payment_walks_forward_to_reference():
    nxt = cu.next_payment_date("2024-01-15", "monthly", 1,
                               reference=date(2024, 3, 1))
    assert nxt == date(2024, 3, 15)


def test_next_payment_returns_future_start_unchanged():
    nxt = cu.next_payment_date("2025-12-01", "monthly", 1,
                               reference=date(2024, 1, 1))
    assert nxt == date(2025, 12, 1)


def test_next_payment_clamps_end_of_month():
    # Jan 31 + 1 month must land on Feb 29 (2024 is a leap year), not overflow.
    nxt = cu.next_payment_date("2024-01-31", "monthly", 1,
                               reference=date(2024, 2, 1))
    assert nxt == date(2024, 2, 29)


def _step_by_step(start: str, frequency: str, interval: int, base_unit, reference: date):
    """The naive walk next_payment_date short-circuits — the reference behaviour."""
    unit, n = cu.resolve(frequency, interval, base_unit)
    d = date.fromisoformat(start)
    while d < reference:
        d = cu._advance(d, unit, n)
    return d


@pytest.mark.parametrize("start,frequency,interval,base_unit,reference", [
    ("2015-02-01", "daily",     1, None,      date(2026, 9, 19)),   # thousands of steps
    ("2015-01-31", "daily",     1, None,      date(2026, 9, 19)),   # month-end anchor
    ("2015-03-15", "weekly",    1, None,      date(2026, 9, 19)),
    ("2015-01-31", "monthly",   1, None,      date(2026, 9, 19)),   # clamps to the 28th
    ("2015-01-30", "monthly",   1, None,      date(2026, 3, 1)),
    ("2015-06-15", "quarterly", 1, None,      date(2026, 9, 19)),
    ("2016-02-29", "yearly",    1, None,      date(2026, 9, 19)),   # leap-day anchor
    ("2015-01-05", "custom",    7, "monthly", date(2026, 9, 19)),
    ("2015-01-05", "custom",    3, "weekly",  date(2026, 9, 19)),
])
def test_next_payment_jump_matches_the_step_by_step_walk(start, frequency, interval,
                                                         base_unit, reference):
    # next_payment_date skips most of the cadence in one jump; the result must be
    # identical to advancing one period at a time (month-end clamping included).
    assert (cu.next_payment_date(start, frequency, interval, base_unit, reference)
            == _step_by_step(start, frequency, interval, base_unit, reference))


# ── upcoming_payments_for_periods / billing-cycle anchoring ──────────────────

_MONTHLY = {"frequency": "monthly", "interval": 1, "base_unit": None}


def test_price_change_keeps_the_original_billing_day():
    # Recorded as a price change: the old period is closed the day before the new
    # one starts. Billing stays on the 20th — it must not move to the 16th.
    periods = [{"amount": 9.99, "start_date": "2026-01-20", "end_date": "2026-06-15"},
               {"amount": 15.99, "start_date": "2026-06-16", "end_date": None}]
    pays = cu.upcoming_payments_for_periods(_MONTHLY, periods, count=3,
                                            reference=date(2026, 9, 1))
    assert [p["date"] for p in pays] == [date(2026, 9, 20), date(2026, 10, 20),
                                         date(2026, 11, 20)]
    assert {p["amount"] for p in pays} == {15.99}


def test_price_change_mid_month_is_not_billed_twice():
    # Bills on the 2nd; the price is raised from the 4th of May. May owes exactly one
    # payment (on the 2nd, still at the old price) — not one per period.
    periods = [{"amount": 59.80, "start_date": "2026-01-02", "end_date": "2026-03-31"},
               {"amount": 55.81, "start_date": "2026-04-01", "end_date": "2026-05-03"},
               {"amount": 54.44, "start_date": "2026-05-04", "end_date": None}]
    pays = cu.upcoming_payments_for_periods(_MONTHLY, periods, count=3,
                                            reference=date(2026, 5, 1))
    assert [(p["date"].isoformat(), p["amount"]) for p in pays] == [
        ("2026-05-02", 55.81), ("2026-06-02", 54.44), ("2026-07-02", 54.44)]


def test_the_period_covering_the_billing_date_sets_the_price():
    periods = [{"amount": 10.0, "start_date": "2026-01-10", "end_date": "2026-03-09"},
               {"amount": 20.0, "start_date": "2026-03-10", "end_date": None}]
    pays = cu.upcoming_payments_for_periods(_MONTHLY, periods, count=4,
                                            reference=date(2026, 2, 1))
    assert [(p["date"].isoformat(), p["amount"]) for p in pays] == [
        ("2026-02-10", 10.0), ("2026-03-10", 20.0),
        ("2026-04-10", 20.0), ("2026-05-10", 20.0)]


def test_a_gap_between_periods_restarts_the_cycle():
    # Cancelled in March, resubscribed in September on a new day: the cycle restarts.
    periods = [{"amount": 10.0, "start_date": "2026-01-12", "end_date": "2026-03-11"},
               {"amount": 10.0, "start_date": "2026-09-25", "end_date": None}]
    pays = cu.upcoming_payments_for_periods(_MONTHLY, periods, count=2,
                                            reference=date(2026, 9, 1))
    assert [p["date"] for p in pays] == [date(2026, 9, 25), date(2026, 10, 25)]


def test_cycle_anchors_follow_contiguity():
    periods = [{"amount": 1, "start_date": "2026-01-05", "end_date": "2026-02-04"},
               {"amount": 2, "start_date": "2026-02-05", "end_date": "2026-03-31"},
               {"amount": 3, "start_date": "2026-06-01", "end_date": None}]
    assert cu.cycle_anchors(periods) == ["2026-01-05", "2026-01-05", "2026-06-01"]


# ── range_cost ───────────────────────────────────────────────────────────────

def test_range_cost_daily_is_exact_over_window():
    sub = {"frequency": "daily", "interval": 1, "base_unit": None}
    periods = [{"amount": 1.0, "start_date": "2024-01-01", "end_date": None}]
    # $1/day across an inclusive 10-day window.
    cost = cu.range_cost(sub, periods, date(2024, 1, 1), date(2024, 1, 10))
    assert cost == 10.0


def test_range_cost_sums_two_priced_periods():
    sub = {"frequency": "daily", "interval": 1, "base_unit": None}
    periods = [
        {"amount": 1.0, "start_date": "2024-01-01", "end_date": "2024-01-05"},  # 5 days
        {"amount": 2.0, "start_date": "2024-01-06", "end_date": "2024-01-10"},  # 5 days
    ]
    cost = cu.range_cost(sub, periods, date(2024, 1, 1), date(2024, 1, 10))
    assert cost == 15.0  # 5*1 + 5*2


def test_range_cost_ignores_periods_outside_window():
    sub = {"frequency": "daily", "interval": 1, "base_unit": None}
    periods = [{"amount": 1.0, "start_date": "2023-01-01", "end_date": "2023-12-31"}]
    assert cu.range_cost(sub, periods, date(2024, 1, 1), date(2024, 1, 10)) == 0.0


def test_range_cost_does_not_compound_a_rounded_daily_rate():
    # €1.99/month is €0.0654/day; rounding that to €0.07 first overstated a year by ~7%.
    sub = {"frequency": "monthly", "interval": 1, "base_unit": None}
    periods = [{"amount": 1.99, "start_date": "2026-01-01", "end_date": None}]
    assert cu.year_cost(sub, periods, 2026) == pytest.approx(1.99 * 12 * 365 / 365.25, abs=0.01)


# ── upcoming_payments_for_periods ────────────────────────────────────────────

def test_upcoming_payments_respects_count_and_amount():
    sub = {"frequency": "monthly", "interval": 1, "base_unit": None}
    periods = [{"amount": 9.99, "start_date": "2024-01-10", "end_date": None}]
    out = cu.upcoming_payments_for_periods(sub, periods, count=3,
                                           reference=date(2024, 1, 1))
    assert [p["date"] for p in out] == [
        date(2024, 1, 10), date(2024, 2, 10), date(2024, 3, 10)]
    assert all(p["amount"] == 9.99 for p in out)


def test_payments_between_is_bounded_by_the_window():
    sub = {"frequency": "monthly", "interval": 1, "base_unit": None}
    periods = [{"amount": 9.99, "start_date": "2024-01-10", "end_date": None}]
    out = cu.payments_between(sub, periods, date(2024, 2, 1), date(2024, 4, 9))
    assert [p["date"] for p in out] == [date(2024, 2, 10), date(2024, 3, 10)]


def test_payments_between_covers_a_whole_year_of_daily_billing():
    sub = {"frequency": "daily", "interval": 1, "base_unit": None}
    periods = [{"amount": 1.0, "start_date": "2020-01-01", "end_date": None}]
    assert len(cu.payments_between(sub, periods, date(2024, 1, 1), date(2024, 12, 31))) == 366
