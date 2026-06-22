# SubTracker

A multi-tenant subscription cost tracker built with [FastHTML](https://fastht.ml)
and SQLite. Track recurring spend across teams, with role-based access control,
period-aware price history, soft-deletes with restore, a tamper-resistant audit
log, and CSV/JSON import-export — all server-rendered, no JavaScript build step.

---

## Features

- **Spend dashboard** — historical spend for any calendar year (prorated over each
  subscription's active windows and price changes), current run-rate, year-over-year
  delta, per-period cost cards, and bar/breakdown charts by subscription, category,
  and billing frequency.
- **Flexible cadences** — daily / weekly / monthly / quarterly / yearly presets,
  plus a `custom` "every N units" option.
- **Price periods** — each subscription owns one or more dated, non-overlapping
  active windows, each with its own price; the dashboard and next-payment forecast
  honour them exactly.
- **Multi-tenant** — subscriptions are owned by a team; users switch between the
  teams they belong to, and a super-admin can view across all teams at once.
- **RBAC** — a global role axis (`super_admin`) and a per-team role axis
  (`team_admin`, `viewer`) compose by union; the role→permission matrix lives in the
  database.
- **Audit log** — every create / update / delete / price change / login is recorded;
  entries are denormalised and FK-free so they survive permanent deletion of the
  records they describe.
- **Soft-delete + restore** — deletes are reversible; permitted roles can view,
  restore, or permanently purge deleted records.
- **Import / export** — round-trip the active team's subscriptions and price periods
  as CSV or JSON.
- **Dark mode** — system-aware theme toggle, no flash on load.

---

## Quick start (local dev)

```bash
uv sync --group dev          # install runtime + test dependencies
uv run python main.py        # http://localhost:5001  (live reload)
```

First visit walks you through creating the initial **super-admin** account.

Run the tests:

```bash
uv run pytest
```

---

## Configuration

All configuration is via environment variables:

| Variable             | Required | Default                  | Purpose                                                        |
| -------------------- | -------- | ------------------------ | -------------------------------------------------------------- |
| `SUBTRACKER_SECRET`  | **Prod** | random per-process       | Session-signing key. **Set a stable value in production** — without it, logins do not survive a restart and a warning is logged. Generate with `openssl rand -hex 32`. |
| `SUBTRACKER_DB`      | no       | `./subscriptions.db`     | SQLite file path. Point at a persistent volume in a container (e.g. `/data/subscriptions.db`). |
| `SUBTRACKER_PORT`    | no       | `5001`                   | Listen port.                                                   |

The database runs in WAL mode and is created automatically on first boot.

---

## Deployment

### Option A — Docker Compose (run anywhere, incl. alongside Home Assistant)

```bash
# 1. Create .env with a stable secret
echo "SUBTRACKER_SECRET=$(openssl rand -hex 32)" > .env

# 2. Build & start
docker compose up -d --build

# 3. Open http://<host>:5001
```

Data persists in the `subtracker-data` named volume. To surface it inside Home
Assistant, add a **Webpage** dashboard card (or a Lovelace `iframe` card) pointing
at `http://<host>:5001`.

### Option B — Home Assistant add-on (add-on store, via repository URL)

This repo is also a **Home Assistant add-on repository** exposing two channels:

- **SubTracker** — stable. Published only when a `v*` release tag is pushed.
- **SubTracker (Nightly)** — bleeding edge. Rebuilt on every push to `master`, with
  its own slug, image, `/data`, and host port (`5002`) so it runs alongside stable.

The Supervisor *pulls a prebuilt image* (it does not build on-device), so images are
published to GHCR by the GitHub Actions workflows.

**One-time publishing setup (maintainer):** after each workflow's first successful
run, make its packages **public** at `https://github.com/users/78wesley/packages`
(*Package settings → Change visibility → Public*) — otherwise the Supervisor can't
pull them. The packages are `subtracker-amd64` / `subtracker-aarch64` (stable) and
`subtracker-nightly-amd64` / `subtracker-nightly-aarch64`.

**Installing in Home Assistant (any user):**

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories** → add
   `https://github.com/78wesley/subtracker`.
2. **SubTracker** (and **SubTracker (Nightly)**) appear in the store. Click **Install**
   on the one you want.
3. On the **Configuration** tab, optionally set `log_level`. (The session key is
   auto-generated and persisted to `/data/.secret` — it is not a user option.)
4. **Start**, then click **Open Web UI**.

The SQLite database lives in the add-on's persistent `/data` directory and is
included in HA snapshots/backups. (Stable and nightly keep separate databases.)

**Cutting a stable release (maintainer):**

```bash
# 1. Bump the version in subtracker/config.yaml, commit it
git commit -am "Release 0.2.0"
# 2. Tag it — this is what triggers the production image build
git tag v0.2.0 && git push origin master v0.2.0
```

[`release.yaml`](.github/workflows/release.yaml) runs the tests, checks the tag
matches `subtracker/config.yaml`, builds + pushes `ghcr.io/78wesley/subtracker-{arch}`,
and opens a GitHub Release. Nightly images and the auto-bumped
`subtracker-nightly/config.yaml` version are handled by
[`nightly.yaml`](.github/workflows/nightly.yaml) on every master push (gated on the
test suite). Pushing to `master` never touches the stable image.

> The `Dockerfile`/`docker-entrypoint.sh` are shared by the image build and
> docker-compose. The entrypoint reads `/data/options.json` when run as an add-on
> and falls back to `SUBTRACKER_*` environment variables otherwise.

---

## Security notes

- Passwords are hashed with **bcrypt** (per-password salt).
- Sessions are signed cookies keyed by `SUBTRACKER_SECRET`.
- Authorization is enforced per-route via the RBAC layer (`app/rbac.py`,
  `app/authz.py`); roles compose by union across a global and a per-team axis.
- CSV export quotes leading formula characters (`=`, `+`, `-`, `@`) to neutralise
  spreadsheet formula injection, and imports are size- and row-capped.

**Recommended hardening before exposing to untrusted networks** (not yet
implemented): CSRF tokens on state-changing forms, login rate-limiting, and
serving behind HTTPS with `Secure` session cookies.

---

## Project layout

```
app/
  main.py            ASGI app assembly + global styles/scripts
  config.py          env-driven configuration
  session.py         auth gate (Beforeware) + request context
  rbac.py / authz.py role catalog, permission resolution, per-route guard
  auth.py            bcrypt hashing + authentication
  cost_utils.py      cadence math, prorated/period-aware cost, next payments
  timeutil.py        central date/time provider
  styles.py          shadcn token CSS + Tailwind utility-class constants
  db/                schema (idempotent + migration), data access per entity
  routes/            one APIRouter per feature area
  components/        FastHTML view helpers (shadcn-styled) + charts
tests/               pytest suite (cost math, RBAC, auth, migration, HTTP smoke)
Dockerfile           production image (used by compose + the GHCR image build)
docker-compose.yml   standalone deployment
repository.yaml      Home Assistant add-on repository manifest
subtracker/          HA add-on (config.yaml → prebuilt GHCR image, DOCS.md)
.github/workflows/   CI that builds & pushes per-arch images to GHCR
```
