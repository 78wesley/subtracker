"""
Dashboard month-billing figures.

These walk real billing dates (what actually lands on the card), so they are
asserted against hand-computed payment schedules rather than the prorated
year-cost maths covered in test_cost_utils.
"""

from datetime import date

from app.routes.dashboard import _charges_in_month, _month_billing, _year_analytics
from tests.conftest import post, setup_first_admin

TODAY = date(2026, 9, 19)


def _sub(sub_id, name, frequency="monthly", interval=1, base_unit=None):
    return {"id": sub_id, "name": name, "frequency": frequency,
            "interval": interval, "base_unit": base_unit}


def _period(amount, start, end=None):
    return {"amount": amount, "start_date": start, "end_date": end}


# ── month billing (pure) ─────────────────────────────────────────────────────

def test_charges_in_month_lists_each_billing_date():
    subs = [_sub(1, "Netflix")]
    pm = {1: [_period(12.99, "2025-03-04")]}
    charges = _charges_in_month(subs, pm, TODAY)
    assert [(c["date"], c["amount"]) for c in charges] == [(date(2026, 9, 4), 12.99)]


def test_charges_in_month_covers_a_daily_subscription():
    subs = [_sub(1, "Daily", "daily")]
    pm = {1: [_period(1.0, "2026-01-01")]}
    assert len(_charges_in_month(subs, pm, TODAY)) == 30  # September


def test_charges_in_month_excludes_ended_periods():
    subs = [_sub(1, "Gone")]
    pm = {1: [_period(9.0, "2025-01-10", "2026-08-31")]}
    assert _charges_in_month(subs, pm, TODAY) == []


def test_charges_in_month_uses_the_price_of_the_period_it_falls_in():
    # Price rose mid-September: the 20th is billed at the new amount.
    subs = [_sub(1, "Netflix")]
    pm = {1: [_period(10.0, "2026-01-20", "2026-09-19"), _period(15.0, "2026-09-20")]}
    assert [c["amount"] for c in _charges_in_month(subs, pm, TODAY)] == [15.0]


def test_month_billing_splits_paid_and_remaining():
    subs = [_sub(1, "Early"), _sub(2, "Late")]
    pm = {1: [_period(10.0, "2026-01-05")],    # bills the 5th → already billed
          2: [_period(25.0, "2026-01-25")]}    # bills the 25th → still to come
    b = _month_billing(subs, pm, TODAY)
    assert (b["this_total"], b["paid_total"], b["remaining_total"]) == (35.0, 10.0, 25.0)
    assert [c["name"] for c in b["remaining"]] == ["Late"]
    assert b["this_count"] == 2


def test_month_billing_separates_already_billed_charges():
    subs = [_sub(1, "Early"), _sub(2, "Late")]
    pm = {1: [_period(10.0, "2026-01-05")],
          2: [_period(25.0, "2026-01-25")]}
    b = _month_billing(subs, pm, TODAY)
    assert [c["name"] for c in b["paid"]] == ["Early"]
    assert [c["name"] for c in b["remaining"]] == ["Late"]


def test_month_billing_compares_against_the_previous_month():
    subs = [_sub(1, "Yearly renewal", "yearly")]
    pm = {1: [_period(99.0, "2024-08-10")]}    # bills every August
    b = _month_billing(subs, pm, TODAY)
    assert (b["this_total"], b["prev_total"]) == (0.0, 99.0)
    assert b["delta"] == -99.0
    assert (b["this_label"], b["prev_label"]) == ("September 2026", "August 2026")


def test_month_billing_rolls_over_january_to_december():
    subs = [_sub(1, "Netflix")]
    pm = {1: [_period(12.0, "2024-12-03")]}
    b = _month_billing(subs, pm, date(2026, 1, 15))
    assert (b["this_label"], b["prev_label"]) == ("January 2026", "December 2025")
    assert (b["this_total"], b["prev_total"]) == (12.0, 12.0)


def test_year_bars_match_the_billing_card_for_each_month():
    # A yearly renewal and a mid-month start: prorating would spread / shrink both,
    # but the bar must show what is actually charged, like the month card does.
    subs = [_sub(1, "Yearly", "yearly"), _sub(2, "Mortgage"), _sub(3, "Netflix")]
    pm = {1: [_period(159.13, "2025-09-11")],
          2: [_period(1184.03, "2026-09-12")],
          3: [_period(10.0, "2026-01-20", "2026-09-19"), _period(15.0, "2026-09-20")]}
    data = _year_analytics(subs, pm, 2026)
    b = _month_billing(subs, pm, TODAY)
    assert data["months"][8] == b["this_total"] == 1358.16
    assert data["month_counts"][8] == b["this_count"] == 3
    assert data["months"][7] == b["prev_total"] == 10.0
    assert data["yearly_total"] == round(sum(data["months"]), 2)
    assert data["prev_total"] == 159.13     # 2025: only the yearly renewal


# ── rendering ────────────────────────────────────────────────────────────────

def _create(client, **over):
    data = {"name": "Netflix", "amount": "12.99", "start_date": "2025-03-04",
            "frequency": "monthly"}
    data.update(over)
    return post(client, "/manage/new", data, token_path="/manage", follow_redirects=True)


def test_dashboard_shows_this_and_last_month(client, db):
    setup_first_admin(client)
    _create(client)
    html = client.get("/dashboard").text
    assert "What you pay this month" in html
    assert "This month" in html and "Last month" in html
    assert "data-tip-label" in html          # charts carry tooltip data


def test_right_now_section_comes_before_the_year_selector(client, db):
    setup_first_admin(client)
    _create(client)
    html = client.get("/dashboard").text
    assert html.index("Right now") < html.index("Calendar year") < html.index("?year=")


def test_dashboard_splits_still_to_pay_from_already_billed(client, db, monkeypatch):
    monkeypatch.setattr("app.timeutil.today", lambda: TODAY)   # freeze at 19 Sep 2026
    setup_first_admin(client)
    _create(client, name="Early", start_date="2026-01-05")     # billed on the 5th
    _create(client, name="Late", start_date="2026-01-25")      # due on the 25th
    html = client.get("/dashboard").text

    assert "Still to pay this month" in html
    assert "1 payment already billed" in html
    assert "data-disclosure" in html                            # the toggle itself
    # The still-due block lists only the upcoming charge; the billed one is behind
    # the toggle, further down the card.
    assert html.index("Still to pay this month") < html.index("already billed")
    assert html.index("Late") < html.index("already billed") < html.index("Early")
