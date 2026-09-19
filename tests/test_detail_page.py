"""
The tabbed subscription detail page: each tab renders its own concern, tabs are
plain links, and period actions come back to the tab they were issued from.
"""

from tests.conftest import post, setup_first_admin


def _create(client, **over):
    data = {"name": "Netflix", "amount": "12.99", "start_date": "2025-03-04",
            "frequency": "monthly"}
    data.update(over)
    return post(client, "/manage/new", data, token_path="/manage", follow_redirects=True)


def test_detail_tabs_render_their_own_content(client, db):
    setup_first_admin(client)
    _create(client)
    sub_id = next(iter(db["subscriptions"].rows))["id"]
    base = f"/subscriptions/{sub_id}/detail"

    overview = client.get(base).text
    assert "Next expected payments" in overview
    assert "Add a period" not in overview           # lives on the Periods tab

    periods = client.get(base + "?tab=periods").text
    assert "Add a period" in periods
    assert "Next expected payments" not in periods

    spend = client.get(base + "?tab=spend").text
    assert "Monthly spend in" in spend

    history = client.get(base + "?tab=history").text
    assert "Created 'Netflix'" in history


def test_unknown_tab_falls_back_to_overview(client, db):
    setup_first_admin(client)
    _create(client)
    sub_id = next(iter(db["subscriptions"].rows))["id"]
    assert "Next expected payments" in client.get(
        f"/subscriptions/{sub_id}/detail?tab=nope").text


def test_period_actions_return_to_the_periods_tab(client, db):
    setup_first_admin(client)
    _create(client)
    sub_id = next(iter(db["subscriptions"].rows))["id"]
    r = post(client, f"/subscriptions/{sub_id}/periods/add",
             {"amount": "15.99", "start_date": "2026-06-01"},
             token_path="/manage", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"/subscriptions/{sub_id}/detail?tab=periods&msg=")
