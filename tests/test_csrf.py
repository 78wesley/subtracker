"""CSRF protection: unsafe requests need a token matching the session."""

from app.auth import create_user
from tests.conftest import csrf_token, login, post


def test_post_without_token_is_rejected(client, db):
    create_user("admin", "password123", global_role="super_admin")
    # A raw POST with no csrf_token field and no header — must be blocked.
    r = client.post("/login", data={"username": "admin", "password": "password123"})
    assert r.status_code == 403
    assert "csrf" in r.text.lower()


def test_post_with_wrong_token_is_rejected(client, db):
    create_user("admin", "password123", global_role="super_admin")
    r = client.post("/login", data={"username": "admin", "password": "password123",
                                    "csrf_token": "not-the-real-token"})
    assert r.status_code == 403


def test_post_with_valid_token_succeeds(client, db):
    create_user("admin", "password123", global_role="super_admin")
    r = login(client, "admin", "password123")  # helper injects the session token
    assert r.status_code == 200
    assert r.url.path == "/dashboard"


def test_htmx_header_token_is_accepted(client, db):
    """HTMX requests carry the token in the X-CSRFToken header, not the body."""
    create_user("admin", "password123", global_role="super_admin")
    login(client, "admin", "password123")
    token = csrf_token(client, "/manage")
    # Deleting a non-existent subscription still passes the CSRF gate (then 303s),
    # proving the header path is accepted; a missing header would 403 instead.
    r = client.post("/subscriptions/99999/delete", headers={"X-CSRFToken": token})
    assert r.status_code != 403


def test_pages_expose_csrf_meta_tag(client):
    """Every rendered page carries the token for the client JS to read."""
    assert csrf_token(client, "/setup")  # setup page (no users yet)
    post(client, "/setup", {"username": "a", "password": "password123",
                            "password2": "password123"},
         token_path="/setup", follow_redirects=True)
    assert csrf_token(client, "/dashboard")  # authenticated page via nav bar
