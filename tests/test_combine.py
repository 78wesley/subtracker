"""
Combining a duplicate subscription into the one it should have been part of.

The case this exists for: an import brings newer prices for a subscription whose
current period is still open-ended, so they land as a second subscription with the
same name. Combining moves those periods across and closes the open-ended one.
"""

from app.db import combine_subscriptions, get_periods, plan_combine
from tests.conftest import csrf_token, post, setup_first_admin


def _periods(*specs):
    """[(id, amount, start, end)] → period dicts as the data layer returns them."""
    return [{"id": i, "amount": a, "start_date": s, "end_date": e} for i, a, s, e in specs]


# ── planning (pure) ──────────────────────────────────────────────────────────

def test_plan_closes_an_open_ended_period_before_the_incoming_one():
    target = _periods((1, 9.99, "2026-01-20", None))
    source = _periods((2, 15.99, "2026-06-16", None))
    err, closes, moved = plan_combine(target, source)
    assert err == ""
    assert closes == {1: "2026-06-15"}       # closed the day before the new period
    assert moved == 1


def test_plan_rejects_a_genuine_overlap():
    target = _periods((1, 9.99, "2026-01-01", "2026-12-31"))
    source = _periods((2, 15.99, "2026-06-01", "2026-08-31"))
    err, closes, moved = plan_combine(target, source)
    assert "overlap" in err.lower()
    assert (closes, moved) == ({}, 0)


def test_plan_leaves_non_overlapping_periods_alone():
    target = _periods((1, 9.99, "2026-01-01", "2026-03-31"))
    source = _periods((2, 15.99, "2026-04-01", None))
    err, closes, moved = plan_combine(target, source)
    assert (err, closes, moved) == ("", {}, 1)


def test_plan_closes_the_incoming_open_period_when_the_target_continues_after_it():
    # Imported history that predates what is already recorded.
    target = _periods((1, 15.99, "2026-06-16", None))
    source = _periods((2, 9.99, "2026-01-20", None))
    err, closes, moved = plan_combine(target, source)
    assert (err, closes, moved) == ("", {2: "2026-06-15"}, 1)


# ── the merge itself ─────────────────────────────────────────────────────────

def _create(client, name, amount="9.99", start="2026-01-20"):
    return post(client, "/manage/new",
                {"name": name, "amount": amount, "start_date": start,
                 "frequency": "monthly"}, token_path="/manage", follow_redirects=True)


def test_combine_moves_periods_and_keeps_their_identity(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    _create(client, "Netflix", amount="15.99", start="2026-06-16")
    moved_id = get_periods(db, 2)[0]["id"]

    err, moved, note = combine_subscriptions(db, 1, 2)
    assert (err, moved) == ("", 1)
    assert "2026-06-15" in note

    periods = get_periods(db, 1)
    assert [(p["amount"], p["start_date"], p["end_date"]) for p in periods] == [
        (9.99, "2026-01-20", "2026-06-15"), (15.99, "2026-06-16", None)]
    assert periods[1]["id"] == moved_id      # re-pointed, not copied
    assert get_periods(db, 2) == []


def test_combine_refuses_to_merge_a_subscription_into_itself(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    err, moved, _ = combine_subscriptions(db, 1, 1)
    assert err and moved == 0


def test_combine_changes_nothing_when_the_periods_overlap(client, db):
    setup_first_admin(client)
    _create(client, "Gym")
    post(client, "/subscriptions/1/periods/1/edit",
         {"amount": "9.99", "start_date": "2026-01-01", "end_date": "2026-12-31"},
         token_path="/manage", follow_redirects=True)
    _create(client, "Gym", amount="12.00", start="2026-06-01")
    post(client, "/subscriptions/2/periods/2/edit",
         {"amount": "12.00", "start_date": "2026-06-01", "end_date": "2026-08-31"},
         token_path="/manage", follow_redirects=True)

    err, moved, _ = combine_subscriptions(db, 1, 2)
    assert "overlap" in err.lower() and moved == 0
    assert len(get_periods(db, 1)) == 1 and len(get_periods(db, 2)) == 1


# ── HTTP: the import prompt and the combine endpoint ─────────────────────────

_CSV = (b"name,category,frequency,interval,base_unit,notes,amount,start_date,end_date\n"
        b"Netflix,,monthly,1,,,15.99,2026-06-16,\n")


def _import(client, body=_CSV, filename="new.csv"):
    return client.post("/import", files={"file": (filename, body, "text/csv")},
                       data={"csrf_token": csrf_token(client, "/import")},
                       follow_redirects=True)


def test_import_offers_to_combine_a_name_that_already_exists(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    html = _import(client).text

    assert "already existed" in html
    assert "/subscriptions/1/combine/2" in html
    # The prompt says what will happen before anything is merged.
    assert "closes the open-ended period on 2026-06-15" in html
    assert db["subscriptions"].count == 2          # nothing merged yet


def test_import_without_a_name_clash_offers_nothing_to_combine(client, db):
    setup_first_admin(client)
    _create(client, "Spotify")
    html = _import(client).text
    assert "combine" not in html.lower()


def test_combine_endpoint_merges_and_soft_deletes_the_duplicate(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    _import(client)

    r = post(client, "/subscriptions/1/combine/2", token_path="/manage",
             follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/subscriptions/1/detail?tab=periods")

    assert db["subscriptions"].get(2)["deleted_at"] is not None
    assert db["subscriptions"].get(1)["deleted_at"] is None
    assert [(p["amount"], p["end_date"]) for p in get_periods(db, 1)] == [
        (9.99, "2026-06-15"), (15.99, None)]
    actions = [a["action"] for a in db["audit_log"].rows]
    assert "COMBINE" in actions


def test_detail_page_offers_to_combine_a_same_named_subscription(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    _import(client)
    html = client.get("/subscriptions/1/detail").text
    assert "named “Netflix”" in html
    assert "/subscriptions/1/combine/2" in html


def test_viewer_is_not_offered_the_combine_action(client, db, monkeypatch):
    from app.auth import create_user
    from app.db import add_member
    setup_first_admin(client)
    _create(client, "Netflix")
    _import(client)
    uid = create_user("vi", "password123", global_role="user")
    add_member(db, 1, uid, "viewer", created_by=uid)

    from tests.conftest import login
    login(client, "vi", "password123")
    html = client.get("/subscriptions/1/detail").text
    assert "/combine/" not in html
    r = post(client, "/subscriptions/1/combine/2", token_path="/manage",
             follow_redirects=True)
    assert "not authorized" in r.text.lower()
    assert db["subscriptions"].get(2)["deleted_at"] is None


def test_combining_across_teams_is_refused(client, db):
    """A super admin in cross-team view can see both rows; merging them would move
    one team's price history into another's."""
    from app.db import add_member, create_team, get_db
    setup_first_admin(client)
    _create(client, "Netflix")                      # team 1
    other = create_team(db, "Other", "", created_by=1)
    add_member(db, other, 1, "team_admin", created_by=1)
    sub_id = db["subscriptions"].insert({
        "team_id": other, "created_by": 1, "name": "Netflix", "currency": "EUR",
        "frequency": "monthly", "interval": 1, "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00"}).last_pk
    from app.db import add_period
    add_period(get_db(), sub_id, 15.99, "2026-06-16", None, 1)

    post(client, "/teams/switch", {"team_id": "__all__"}, token_path="/teams",
         follow_redirects=True)
    r = post(client, f"/subscriptions/1/combine/{sub_id}", token_path="/manage",
             follow_redirects=False)
    assert "different" in r.headers["location"]
    assert db["subscriptions"].get(sub_id)["deleted_at"] is None
    assert len(get_periods(db, 1)) == 1
