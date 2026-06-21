"""End-to-end HTTP smoke tests through the real ASGI app (isolated DB per test)."""

from app.auth import create_user


def test_fresh_install_redirects_to_setup(client):
    r = client.get("/login", follow_redirects=True)
    assert r.status_code == 200
    assert "Create your admin account" in r.text


def test_setup_creates_admin_and_logs_in(client):
    r = client.post("/setup", data={
        "username": "admin",
        "password": "password123",
        "password2": "password123",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert r.url.path == "/dashboard"


def test_setup_rejects_mismatched_passwords(client):
    r = client.post("/setup", data={
        "username": "admin", "password": "aaaaaa", "password2": "bbbbbb",
    }, follow_redirects=True)
    assert r.url.path == "/setup"
    assert "do not match" in r.text.lower()


def test_setup_rejects_short_password(client):
    r = client.post("/setup", data={
        "username": "admin", "password": "short", "password2": "short",
    }, follow_redirects=True)
    assert r.url.path == "/setup"
    assert "at least 6" in r.text.lower()


def test_protected_page_redirects_to_login_when_unauthenticated(client, db):
    create_user("admin", "password123", global_role="super_admin")  # users exist
    r = client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert r.url.path == "/login"
    assert "Sign In" in r.text


def test_bad_login_is_rejected(client, db):
    create_user("admin", "password123", global_role="super_admin")
    r = client.post("/login", data={"username": "admin", "password": "wrong"},
                    follow_redirects=True)
    assert r.url.path == "/login"
    assert "invalid" in r.text.lower()


def test_login_then_reach_dashboard(client, db):
    create_user("admin", "password123", global_role="super_admin")
    r = client.post("/login", data={"username": "admin", "password": "password123"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert r.url.path == "/dashboard"
