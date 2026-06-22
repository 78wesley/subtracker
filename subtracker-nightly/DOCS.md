# SubTracker (Nightly)

The **bleeding-edge** channel of SubTracker. Every commit to `master` publishes a
new image and Home Assistant will offer it as an update. Expect rough edges — for
day-to-day use, install the stable **SubTracker** add-on instead.

## Nightly vs. stable

- **Separate add-on**: own slug, own image, and its **own `/data`** — the nightly
  database is independent of stable, so trying it out won't touch your real data.
- **Default host port `5002`** (stable uses `5001`) so both can run at once.
- New version on every master commit; the version number is `<date>.<build>`.

> Migrating data between channels isn't automatic. Use the stable add-on's
> **Import / Export** page to move subscriptions between the two if you want to.

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories** →
   `https://github.com/78wesley/subtracker`.
2. The **SubTracker (Nightly)** add-on appears in the store. Click **Install**.
3. On the **Configuration** tab, optionally set options (see below), then
   **Start** and click **Open Web UI**.

The first visit walks you through creating the initial admin account.

## Options

| Option       | Default | Description                             |
| ------------ | ------- | --------------------------------------- |
| `log_level`  | `info`  | uvicorn log level (`trace`…`critical`). |

The session-signing key is generated and persisted automatically under
`/data/.secret`; it is not a user option.
