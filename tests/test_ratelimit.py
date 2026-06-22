"""Auth rate limiting: the RateLimiter unit + the /login integration."""

from app.auth import create_user
from app.ratelimit import RateLimiter, login_limiter
from tests.conftest import post


def test_limiter_allows_up_to_max_then_blocks():
    rl = RateLimiter(max_attempts=3, window_seconds=300)
    for _ in range(3):
        assert not rl.is_limited("ip")
        rl.record("ip")
    assert rl.is_limited("ip")


def test_limiter_is_per_key():
    rl = RateLimiter(max_attempts=1, window_seconds=300)
    rl.record("a")
    assert rl.is_limited("a")
    assert not rl.is_limited("b")


def test_reset_clears_state():
    rl = RateLimiter(max_attempts=1, window_seconds=300)
    rl.record("a")
    rl.reset("a")
    assert not rl.is_limited("a")


def test_login_is_throttled_after_too_many_attempts(client, db):
    create_user("admin", "password123", global_role="super_admin")
    # Exhaust the allowance with wrong passwords.
    for _ in range(login_limiter.max_attempts):
        post(client, "/login", {"username": "admin", "password": "wrong"},
             follow_redirects=True)
    # The next attempt — even with the CORRECT password — is rate-limited.
    r = post(client, "/login", {"username": "admin", "password": "password123"},
             follow_redirects=True)
    assert r.url.path == "/login"
    assert "too many attempts" in r.text.lower()
