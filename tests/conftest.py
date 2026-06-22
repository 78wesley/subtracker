"""
Shared test fixtures.

Each test gets an isolated SQLite file: we point `app.db.connection.DB_PATH` at a
per-test temp file (the app reads the DB through `get_db()` on every call, so this
redirects both direct data-layer tests and live request handlers).
"""

import os
import re

# Set before any `app` import so config-time reads pick them up.
os.environ.setdefault("SUBTRACKER_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("SUBTRACKER_DB", "/tmp/subtracker-test-import.db")

import pytest

_CSRF_META_RE = re.compile(r'name="csrf-token"\s+content="([^"]*)"')


def csrf_token(client, path: str = "/login") -> str:
    """Scrape the per-session CSRF token from a rendered page's <meta> tag."""
    html = client.get(path, follow_redirects=True).text
    m = _CSRF_META_RE.search(html)
    return m.group(1) if m else ""


def post(client, url: str, data: dict | None = None, token_path: str = "/login", **kwargs):
    """POST with the session's CSRF token injected (as the client JS would)."""
    data = dict(data or {})
    data.setdefault("csrf_token", csrf_token(client, token_path))
    return client.post(url, data=data, **kwargs)


def setup_first_admin(client, username: str = "admin", password: str = "password123"):
    """Run first-run /setup, leaving `client` logged in as the super admin."""
    return post(client, "/setup",
                {"username": username, "password": password, "password2": password},
                token_path="/setup", follow_redirects=True)


def login(client, username: str, password: str):
    """Log `client` in over HTTP (sets the session cookie)."""
    return post(client, "/login", {"username": username, "password": password},
                follow_redirects=True)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the process-global auth rate limiter so tests don't bleed into each other."""
    from app.ratelimit import login_limiter
    login_limiter.reset()
    yield
    login_limiter.reset()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Redirect the data layer to a fresh per-test database file."""
    p = tmp_path / "test.db"
    monkeypatch.setattr("app.db.connection.DB_PATH", p)
    return p


@pytest.fixture
def db(db_path):
    """An initialised (schema + RBAC seed) empty database."""
    from app.db.schema import init_db
    return init_db()


@pytest.fixture
def client(db):
    """A Starlette TestClient bound to the per-test database."""
    from starlette.testclient import TestClient

    from app.main import app
    return TestClient(app)


@pytest.fixture
def seed_team(db):
    """A super-admin user + a team they administer. Returns (uid, team_id)."""
    from app.auth import create_user
    from app.db import add_member, create_team
    uid = create_user("admin", "password123", global_role="super_admin")
    team_id = create_team(db, "Acme", "Acme team", created_by=uid)
    add_member(db, team_id, uid, "team_admin", created_by=uid)
    return uid, team_id
