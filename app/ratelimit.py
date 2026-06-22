"""
ratelimit.py — Minimal in-memory fixed-window rate limiting for auth endpoints.

Guards /login and /setup against online brute-forcing. State is per-process (a
plain dict of monotonic timestamps), which is the right scope for this app's
single-worker deployment; it intentionally adds no external dependency. Restarting
the process clears the counters, and a multi-worker deployment would need a shared
store — both acceptable trade-offs for a self-hosted tool.
"""

import time
from collections import defaultdict, deque


class RateLimiter:
    """Allow at most `max_attempts` recorded hits per key within `window` seconds."""

    def __init__(self, max_attempts: int, window_seconds: float):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque:
        dq = self._hits[key]
        while dq and dq[0] <= now - self.window:
            dq.popleft()
        return dq

    def is_limited(self, key: str) -> bool:
        """True if `key` has already used up its allowance for the current window."""
        return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def record(self, key: str) -> None:
        """Record one attempt against `key`."""
        now = time.monotonic()
        self._prune(key, now).append(now)

    def reset(self, key: str | None = None) -> None:
        """Clear one key, or all keys when `key` is None (used by tests)."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


# Auth limiter: 10 attempts per 5 minutes per client. Generous enough that a human
# fat-fingering a password is unaffected, tight enough to throttle a script.
login_limiter = RateLimiter(max_attempts=10, window_seconds=300)


def client_key(req) -> str:
    """Best-effort client identity for rate-limiting (proxy-aware)."""
    fwd = req.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.client.host if req.client else "unknown"
