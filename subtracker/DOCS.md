# SubTracker

Multi-tenant subscription cost tracker (FastHTML + SQLite).

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories** →
   `https://github.com/78wesley/subtracker`.
2. The **SubTracker** add-on appears in the store. Click **Install**
   (the Supervisor pulls the prebuilt image — no on-device build).
3. On the **Configuration** tab, optionally set options (see below), then
   **Start** and click **Open Web UI**.

The first visit walks you through creating the initial admin account.

## Options

| Option       | Default | Description                             |
| ------------ | ------- | --------------------------------------- |
| `log_level`  | `info`  | uvicorn log level (`trace`…`critical`). |

The session-signing key is handled automatically: the add-on generates one on
first start and persists it to `/data/.secret`, so logins survive restarts. It is
not a user option.

## Data & backups

The SQLite database lives at `/data/subscriptions.db` in the add-on's persistent
storage and is included in Home Assistant snapshots/backups.

## Networking

The web UI is exposed on host port **5001** by default. Change the host port on
the **Network** tab if it clashes with another service.

example:
![image](https://raw.githubusercontent.com/78wesley/subtracker/refs/heads/master/subtracker/img/ui-compare.png)
