"""
Shared test fixtures.

Each test gets an isolated SQLite file: we point `app.db.connection.DB_PATH` at a
per-test temp file (the app reads the DB through `get_db()` on every call, so this
redirects both direct data-layer tests and live request handlers).
"""

import os

# Set before any `app` import so config-time reads pick them up.
os.environ.setdefault("SUBTRACKER_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("SUBTRACKER_DB", "/tmp/subtracker-test-import.db")

import pytest


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
    from app.db import create_team, add_member
    uid = create_user("admin", "password123", global_role="super_admin")
    team_id = create_team(db, "Acme", "Acme team", created_by=uid)
    add_member(db, team_id, uid, "team_admin", created_by=uid)
    return uid, team_id
