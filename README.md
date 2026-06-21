# SubTracker

A multi-tenant subscription cost tracker built with [FastHTML](https://fastht.ml)
and SQLite. Teams, role-based access control, soft-deletes, a tamper-resistant
audit log, period-aware price history, and CSV/JSON import-export.

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

This repo is also a **Home Assistant add-on repository**. The Supervisor *pulls a
prebuilt image* (it does not build on-device), so images must be published to GHCR
first via the included GitHub Actions workflow.

**One-time publishing setup (maintainer):**

1. Push to `master` (or run the **Build add-on images** workflow manually). The
   workflow in [`.github/workflows/build.yaml`](.github/workflows/build.yaml)
   builds `amd64` + `aarch64` images and pushes them to
   `ghcr.io/78wesley/subtracker-{arch}`, tagged with the `version` from
   [`subtracker/config.yaml`](subtracker/config.yaml).
2. Make the published packages **public**: open
   `https://github.com/users/78wesley/packages`, and for both `subtracker-amd64`
   and `subtracker-aarch64` set *Package settings → Change visibility → Public*.
   (Otherwise the Supervisor can't pull them.)

**Installing in Home Assistant (any user):**

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories** → add
   `https://github.com/78wesley/fasthtml-subtracker`.
2. **SubTracker** appears in the store. Click **Install**.
3. On the **Configuration** tab, optionally set `secret_key` (blank = auto-generated
   and persisted to `/data/.secret`) and `log_level`.
4. **Start**, then click **Open Web UI**.

To release an update: bump `version` in `subtracker/config.yaml`, commit, and push
— CI publishes the new tag and HA offers the update. The SQLite database lives in
the add-on's persistent `/data` directory and is included in HA snapshots/backups.

> The `Dockerfile`/`docker-entrypoint.sh` are shared by the image build and
> docker-compose. The entrypoint reads `/data/options.json` when run as an add-on
> and falls back to `SUBTRACKER_*` environment variables otherwise.

---

## Security notes

- Passwords are hashed with **bcrypt** (per-password salt).
- Sessions are signed cookies keyed by `SUBTRACKER_SECRET`.
- Authorization is enforced per-route via the RBAC layer (`app/rbac.py`,
  `app/authz.py`); roles compose by union across a global and a per-team axis.

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
  db/                schema (idempotent + migration), data access per entity
  routes/            one APIRouter per feature area
  components/        FastHTML view helpers (shadcn-styled)
tests/               pytest suite (cost math, RBAC, auth, migration, HTTP smoke)
Dockerfile           production image (used by compose + the GHCR image build)
docker-compose.yml   standalone deployment
repository.yaml      Home Assistant add-on repository manifest
subtracker/          HA add-on (config.yaml → prebuilt GHCR image, DOCS.md)
.github/workflows/   CI that builds & pushes per-arch images to GHCR
```
