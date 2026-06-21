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
