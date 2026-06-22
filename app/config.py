"""
config.py — Central configuration: secret key, DB path, server port.
"""

import os
import secrets
import sys
from pathlib import Path

# Repo root is the parent of the app/ package.
ROOT = Path(__file__).resolve().parent.parent

# Database location. Override with SUBTRACKER_DB to point at a persistent volume
# (e.g. /data/subscriptions.db in a container). Defaults to the repo root for dev.
DB_PATH = Path(os.environ.get("SUBTRACKER_DB", ROOT / "subscriptions.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Session-signing key. MUST be set in production via SUBTRACKER_SECRET — a known,
# hardcoded key would let anyone forge a session cookie and impersonate any user.
# When unset we fall back to a random per-process key (logins just don't survive a
# restart) rather than shipping a guessable default.
SECRET_KEY = os.environ.get("SUBTRACKER_SECRET")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("⚠️  SUBTRACKER_SECRET is not set — using a random ephemeral key. "
          "Logins will not persist across restarts. Set SUBTRACKER_SECRET in the "
          "environment for production.", file=sys.stderr)

PORT = int(os.environ.get("SUBTRACKER_PORT", "5001"))


def _flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag (1/true/yes/on)."""
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Cookie hardening for production behind HTTPS. When SUBTRACKER_SECURE_COOKIES is
# enabled the session cookie is marked Secure (browsers only send it over HTTPS)
# and SameSite is tightened to 'strict'. Left off by default so plain-HTTP local
# dev still works; turn it on for any internet-facing deployment.
SECURE_COOKIES = _flag("SUBTRACKER_SECURE_COOKIES", False)
SESSION_SAMESITE = "strict" if SECURE_COOKIES else "lax"
