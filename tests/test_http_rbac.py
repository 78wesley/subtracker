"""Permission enforcement at the HTTP layer (not just the resolver)."""

import pytest

from app.auth import create_user
from app.db import add_member, create_team
from tests.conftest import login, post


@pytest.fixture
def team(db):
    """A team owned by a super admin; returns its id."""
    owner = create_user("owner", "password123", global_role="super_admin")
    return create_team(db, "Acme", "", created_by=owner)


def _member(db, team_id, username, role):
    uid = create_user(username, "password123", global_role="user")
    add_member(db, team_id, uid, role, created_by=uid)
    return uid


def test_viewer_cannot_open_new_subscription_form(client, db, team):
    _member(db, team, "vi", "viewer")
    login(client, "vi", "password123")
    r = client.get("/manage/new")
    assert "not authorized" in r.text.lower()


def test_viewer_cannot_create_subscription(client, db, team):
    _member(db, team, "vi", "viewer")
    login(client, "vi", "password123")
    r = post(client, "/manage/new", {
        "name": "Sneaky", "amount": "9.99", "start_date": "2026-01-01",
    }, token_path="/manage", follow_redirects=True)
    assert "not authorized" in r.text.lower()
    assert db["subscriptions"].count == 0


def test_viewer_manage_page_hides_create_and_actions(client, db, team):
    _member(db, team, "vi", "viewer")
    login(client, "vi", "password123")
    r = client.get("/manage")
    assert r.status_code == 200
    assert "/manage/new" not in r.text   # no Add link
    assert "Actions" not in r.text       # no per-row actions column


def test_team_admin_can_open_form_and_create(client, db, team):
    _member(db, team, "ta", "team_admin")
    login(client, "ta", "password123")
    assert "Add Subscription" in client.get("/manage/new").text
    post(client, "/manage/new", {
        "name": "Netflix", "amount": "12.99", "start_date": "2026-01-01",
        "frequency": "monthly",
    }, token_path="/manage", follow_redirects=True)
    assert db["subscriptions"].count == 1


def test_viewer_cannot_reach_admin_or_users_pages(client, db, team):
    _member(db, team, "vi", "viewer")
    login(client, "vi", "password123")
    assert "not authorized" in client.get("/admin/deleted").text.lower()
    assert "not authorized" in client.get("/users").text.lower()


def test_viewer_detail_page_has_no_history_tab_or_period_form(client, db, team):
    """A viewer sees the read-only tabs only; ?tab=history falls back to Overview."""
    from app.db import add_period, get_db
    owner = db["users"].get(1)["id"]
    sub_id = db["subscriptions"].insert({
        "team_id": team, "created_by": owner, "name": "Netflix", "currency": "EUR",
        "frequency": "monthly", "interval": 1, "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00"}).last_pk
    add_period(get_db(), sub_id, 12.99, "2026-01-01", None, owner)

    _member(db, team, "vi", "viewer")
    login(client, "vi", "password123")

    overview = client.get(f"/subscriptions/{sub_id}/detail")
    assert overview.status_code == 200
    assert "?tab=history" not in overview.text
    assert "Next expected payments" in overview.text

    periods = client.get(f"/subscriptions/{sub_id}/detail?tab=periods").text
    assert "Add a period" not in periods              # no edit rights
    assert "Next expected payments" in client.get(
        f"/subscriptions/{sub_id}/detail?tab=history").text   # falls back
