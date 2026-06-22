#!/usr/bin/env bash
#
# Unified entrypoint. Resolves the session secret + log level, then execs uvicorn.
#
#   • Home Assistant add-on: the Supervisor writes user options to /data/options.json.
#     We read `log_level` from there (the session secret is always auto-generated below).
#   • docker / compose: configuration comes from SUBTRACKER_* / LOG_LEVEL env vars.
#
# If no secret is provided either way, we generate one once and persist it to
# /data/.secret so logins survive restarts (instead of a random per-process key).
set -euo pipefail

OPTIONS_FILE="/data/options.json"
LOG_LEVEL="${LOG_LEVEL:-info}"

# Pull the log level from the HA add-on config when present (jq isn't installed;
# use python). The session secret is not an add-on option — see below.
if [ -f "$OPTIONS_FILE" ]; then
  opt_log="$(python -c "import json;print(json.load(open('$OPTIONS_FILE')).get('log_level') or '')" 2>/dev/null || true)"
  [ -n "$opt_log" ] && LOG_LEVEL="$opt_log"
fi

# No secret from env or options → reuse/create a persisted one.
if [ -z "${SUBTRACKER_SECRET:-}" ]; then
  mkdir -p /data
  if [ ! -s /data/.secret ]; then
    python -c "import secrets;open('/data/.secret','w').write(secrets.token_hex(32))"
    chmod 600 /data/.secret
  fi
  export SUBTRACKER_SECRET="$(cat /data/.secret)"
fi

export SUBTRACKER_DB="${SUBTRACKER_DB:-/data/subscriptions.db}"
PORT="${SUBTRACKER_PORT:-5001}"

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --log-level "$LOG_LEVEL"
