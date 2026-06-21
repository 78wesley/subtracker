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


# ── upcoming_payments_for_periods ────────────────────────────────────────────

def test_upcoming_payments_respects_count_and_amount():
    sub = {"frequency": "monthly", "interval": 1, "base_unit": None}
    periods = [{"amount": 9.99, "start_date": "2024-01-10", "end_date": None}]
    out = cu.upcoming_payments_for_periods(sub, periods, count=3,
                                           reference=date(2024, 1, 1))
    assert [p["date"] for p in out] == [
        date(2024, 1, 10), date(2024, 2, 10), date(2024, 3, 10)]
    assert all(p["amount"] == 9.99 for p in out)
