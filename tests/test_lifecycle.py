"""Subscription lifecycle over HTTP: create → edit → soft-delete → restore."""

from tests.conftest import post, setup_first_admin


def _create(client, **over):
    data = {"name": "Netflix", "amount": "12.99", "start_date": "2026-01-01",
            "frequency": "monthly"}
    data.update(over)
    return post(client, "/manage/new", data, token_path="/manage", follow_redirects=True)


def test_full_lifecycle(client, db):
    setup_first_admin(client)  # super admin + Default team, logged in

    _create(client, name="Netflix")
    sub = next(iter(db["subscriptions"].rows))
    sub_id = sub["id"]
    assert sub["name"] == "Netflix"
    assert db["subscription_periods"].count == 1  # first period created

    # Edit identity/cadence.
    post(client, f"/subscriptions/{sub_id}/edit",
         {"name": "Netflix Premium", "frequency": "monthly"},
         token_path="/manage", follow_redirects=True)
    assert db["subscriptions"].get(sub_id)["name"] == "Netflix Premium"

    # Soft-delete: row stays but is marked deleted.
    post(client, f"/subscriptions/{sub_id}/delete", token_path="/manage",
         follow_redirects=True)
    assert db["subscriptions"].get(sub_id)["deleted_at"] is not None

    # It disappears from the manage list...
    assert "Netflix Premium" not in client.get("/manage").text
    # ...but appears under deleted records...
    assert "Netflix Premium" in client.get("/admin/deleted").text

    # Restore: deleted markers cleared, visible again.
    post(client, f"/admin/deleted/subscription/{sub_id}/restore",
         token_path="/admin/deleted", follow_redirects=True)
    assert db["subscriptions"].get(sub_id)["deleted_at"] is None
    assert "Netflix Premium" in client.get("/manage").text


def test_permanent_delete_removes_row_but_keeps_audit(client, db):
    setup_first_admin(client)
    _create(client, name="Spotify")
    sub_id = next(iter(db["subscriptions"].rows))["id"]

    post(client, f"/subscriptions/{sub_id}/delete", token_path="/manage",
         follow_redirects=True)
    post(client, f"/admin/deleted/subscription/{sub_id}/purge",
         token_path="/admin/deleted", follow_redirects=True)

    assert db["subscriptions"].count == 0
    # Audit history survives the row (no FK back to it).
    actions = [a["action"] for a in db["audit_log"].rows if a["entity_id"] == sub_id]
    assert "PERMANENT_DELETE" in actions
