# SubTracker

Multi-tenant subscription cost tracker (FastHTML + SQLite).

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories** →
   `https://github.com/78wesley/fasthtml-subtracker`.
2. The **SubTracker** add-on appears in the store. Click **Install**
   (the Supervisor pulls the prebuilt image — no on-device build).
3. On the **Configuration** tab, optionally set options (see below), then
   **Start** and click **Open Web UI**.

The first visit walks you through creating the initial admin account.

## Options

| Option       | Default | Description                                                                 |
| ------------ | ------- | --------------------------------------------------------------------------- |
| `secret_key` | _blank_ | Session-signing key. Leave blank and the add-on generates one and persists it to `/data/.secret` so logins survive restarts. Set your own with `openssl rand -hex 32` if you prefer. |
| `log_level`  | `info`  | uvicorn log level (`trace`…`critical`).                                     |

## Data & backups

The SQLite database lives at `/data/subscriptions.db` in the add-on's persistent
storage and is included in Home Assistant snapshots/backups.

## Networking

The web UI is exposed on host port **5001** by default. Change the host port on
the **Network** tab if it clashes with another service.
