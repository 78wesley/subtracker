"""
config.py — Central configuration: secret key, DB path, server port.
"""

import os
import secrets
import sys
from pathlib import Path

# Repo root is the parent of the app/ package.
ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / "subscriptions.db"

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
