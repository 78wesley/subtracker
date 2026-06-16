# SubTracker Rearchitecture — Design & Delivery Plan

## Context

SubTracker began as a single-user subscription tracker: one 1,538-line `main.py`
mixing routes, UI, and logic; data owned per `user_id`; **no roles** (any logged-in
user can manage all users and hard-delete rows that audit-log foreign keys point at);
a fake "soft delete" that just flips `is_active`; and an audit log that breaks when its
referenced user is deleted.

This rearchitecture turns it into a **multi-tenant, RBAC, audit-compliant** platform:
team-owned data with strict isolation, a permission-based authorization model, real
soft-delete + permanent-delete, and an immutable snapshot audit log. The code is split
into a maintainable Python package.

**Decisions taken with the owner:**
- **Full build, delivered in 3 reviewable phases**, each runnable and committed separately.
- **Fresh start**: existing data is wiped (DB backed up to `subscriptions.db.bak.*`). No row migration.
- **Modularize** `main.py` into an `app/` package.

---

## 1. Updated database schema

All tables get real soft-delete (`deleted_at` NULL = live, `deleted_by` = actor id snapshot).
Roles, permissions, and the role→permission matrix are stored as rows (seeded each boot from the
code source of truth), but the model is **three fixed roles** — Super Admin, Team Admin, Viewer —
with non-editable permission sets. Permission *strings* are a fixed catalog in code (enforcement
references them); operators assign roles, not individual permissions.

```
users              id, username, password_hash, global_role,
                   created_at, deleted_at, deleted_by            -- unique(username)
teams              id, name, slug, description,
                   created_at, created_by, deleted_at, deleted_by -- unique(slug)
team_members       id, team_id, user_id, team_role,
                   created_at, created_by, deleted_at, deleted_by
                   -- partial-unique(team_id,user_id) WHERE deleted_at IS NULL
roles              name (pk), scope('global'|'team'), label, is_system, rank
permissions        name (pk), label, category
role_permissions   role_name, permission_name (composite pk)     -- the editable matrix
subscriptions      id, team_id, created_by, name, amount, currency, category,
                   start_date, end_date, notes,
                   frequency, interval, base_unit, is_active,
                   created_at, updated_at, deleted_at, deleted_by
                   -- index(team_id, deleted_at)
subscription_price_history  id, subscription_id, amount, valid_from,
                   created_at, created_by
audit_log          id, actor_user_id, actor_name, actor_global_role,
                   team_id, team_name, action, entity_type, entity_id,
                   entity_name, old_values(json), new_values(json),
                   description, timestamp                          -- NO foreign keys
```

**Field model changes**
- `subscriptions.user_id` → `team_id` (ownership moves to the team) + `created_by` (who made it).
- `repeat_unit` → `frequency`; `repeat_skip` → `interval`; new `base_unit` (see §"Frequency model").
- `is_active` stays as *business state* (active/inactive). `deleted_at` is the new, orthogonal
  *lifecycle* axis. The old delete that overloaded `is_active`+`end_date` is removed.

**Foreign keys — deliberate choices.** `get_db()` opens a fresh connection per call and SQLite has
`foreign_keys` OFF by default, so FKs are inert and are **not** the security boundary — the scoped
query helper (§7) is. We keep intra-tenant FKs as documentation (`price_history.subscription_id`,
`team_members.{team_id,user_id}`) and **deliberately use no FK** on `audit_log` or on the role-name
columns, so audit survives permanent deletion and role-row edits never throw on the per-request connection.

### Frequency model
`frequency ∈ {daily, weekly, monthly, quarterly, yearly, custom}`.
- The five **named** frequencies are presets (`interval = 1`, `base_unit = NULL`).
- **`custom`** carries `base_unit ∈ {daily, weekly, monthly, yearly}` + `interval = N` → "every N units".
- Old `halfyear` becomes `custom / monthly / 6`; old "every 2 months" becomes `custom / monthly / 2`.
- Cost math resolves `(effective_unit, n)`: named → `(frequency, 1)`, custom → `(base_unit, interval)`,
  then the existing day-count arithmetic is unchanged (`halfyear`'s 182.625 days = monthly × 6 falls out naturally).

---

## 2. ERD (relationships)

```
              ┌────────────┐         ┌──────────────────┐         ┌─────────────┐
              │   users    │1───────*│   team_members   │*───────1│    teams    │
              │ global_role│         │ team_role        │         │             │
              └─────┬──────┘         └──────────────────┘         └──────┬──────┘
                    │ created_by                                          │1
                    │                                                     │
                    │                                              *      ▼
                    │                                       ┌──────────────────────┐
                    │                                       │     subscriptions    │
                    │                                       │ team_id, created_by  │
                    │                                       └───────────┬──────────┘
                    │                                                   │1
                    │                                                   ▼ *
                    │                                  ┌───────────────────────────────┐
                    │                                  │  subscription_price_history    │
                    │                                  └───────────────────────────────┘
   roles 1───* role_permissions *───1 permissions     (roles.name ← users.global_role / team_members.team_role, by value)

   audit_log : standalone, no FKs — snapshots actor_name, team_name, entity_name (survives any deletion)
```

**Recommendations:** index `subscriptions(team_id, deleted_at)` (hot path), `team_members(team_id)` and
`(user_id)`, `audit_log(team_id)` and `(entity_type, entity_id)`. Enforce one live membership per
`(team_id,user_id)` with a partial-unique index.

---

## 3. Migration plan (fresh start)

1. Back up `subscriptions.db` (done). 2. Delete the live DB once so the new schema is created clean.
3. `init_db()` is **idempotent**: create-if-absent tables + add-column-if-absent, then `seed_rbac()`
   upserts the fixed `roles`, `permissions`, and the default `role_permissions` matrix every boot
   (composite PKs make re-seeding safe). 4. `/setup` creates the first user as **`global_role=super_admin`**,
   creates a default team, and links them as `team_admin`. No backwards-compat shims (fresh DB, no legacy CSV/audit).
   Between phases, because the DB holds only dev/test data, it is simply recreated when structural columns change.

---

## 4. API / route changes

Route **paths stay byte-identical** through Phase 1 (pure mechanical move) to keep the refactor reviewable.
New routes arrive in Phase 2–3:

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/teams/switch` | `teams.view` | set active team in session (re-verifies membership) |
| POST | `/teams/view-all` | (super_admin) | toggle cross-team view |
| GET/POST | `/teams`, `/teams/{id}` | `teams.manage` | create/rename/delete teams |
| GET/POST | `/teams/{id}/members` | `teams.manage` | add/remove members, change team_role |
| GET | `/admin/deleted` | `records.view_deleted` | soft-deleted records |
| POST | `/admin/deleted/{type}/{id}/restore` | `records.restore` | |
| POST | `/admin/deleted/{type}/{id}/purge` | `subscriptions.delete.permanent` | hard delete, audited |
| GET | `/admin/roles` | `settings.manage` | read-only role → permission reference |

Existing handlers gain a `require(ctx, "<perm>")` gate and load rows through the team-scoped helper
(§7) instead of `WHERE user_id = ?`. `guard(session)` is replaced by a single `Beforeware`.

---

## 5. Roles & permission matrix

There are **exactly three assignable roles with FIXED permission sets** (not editable — no
per-permission toggling). Permissions are an internal enforcement detail; operators only ever
*assign a role*. `user` is the implicit baseline for a normal account (no global powers, no
permissions of its own) — assigned via the Users page as "User".

- **Super Admin** — global; every permission on every team. Assigned on the Users page.
- **Team Admin** — per team; full management of their team (subscriptions + members + restore/purge + team audit).
- **Viewer** — per team; read-only. Both team roles are assigned on each team's Members page.

Effective permissions for a `(user, active_team)` pair = the user's global-role perms **unioned**
with the active team's team-role perms (only if a live membership exists). `super_admin` short-circuits
to all permissions. No deny rules (union only → simple, auditable). The `/admin/roles` page is a
**read-only reference** of this matrix.

**Permission catalog:** `subscriptions.view|create|edit|delete|delete.permanent`,
`records.restore|view_deleted`, `teams.view|manage`, `users.view|manage`, `audit.view`, `settings.manage`.

| Permission | Super Admin (global) | Team Admin (team) | Viewer (team) |
|---|:--:|:--:|:--:|
| subscriptions.view | ● | ● | ● |
| subscriptions.create / edit / delete | ● | ● | — |
| subscriptions.delete.permanent | ● | ● | — |
| records.restore / view_deleted | ● | ● | — |
| teams.view | ● | ● | ● |
| teams.manage (this team) | ● | ● | — |
| audit.view | ● (all) | ● (this team) | own actions |
| users.view / users.manage | ● | — | — |
| settings.manage | ● | — | — |

A plain **User** (baseline, no team role) has no permissions until added to a team as Viewer or Team Admin.

---

## 6. UI / UX improvements

- **Table text wrapping:** `td { white-space:normal; overflow-wrap:anywhere; word-break:break-word; vertical-align:top; max-width:22rem }`, `th { white-space:nowrap }`, opt-out `.nowrap` for dates/amounts/status. Long cells use a 2-line CSS clamp with the full text in the native `title=` attribute (tooltip, no JS) — the `truncate()` helper stops discarding the tail.
- **Team switcher** in nav (auto-submit `<select>`, mirrors the dashboard year selector), shown when the user has ≥1 team.
- **Role-gated nav:** `Users`/`Teams`/`Admin`/`Debug` links render only if the active perms allow them.
- **Deleted-records admin view** with Restore + Permanent-delete (confirm) actions, reusing the `.action-menu` dropdown.
- **Team & member management** screens; **role→permission matrix** rendered read-only (roles are fixed: Super Admin / Team Admin / Viewer).

---

## 7. Security considerations

- **One choke point:** all team-scoped reads go through `team_query(ctx, perm=…, include_deleted=False)`,
  which returns a `(where, params)` fragment already scoped to the caller's authorized team(s) **and**
  gated on a permission, and appends `deleted_at IS NULL` by default. The old `WHERE user_id=?` helpers are
  **removed**, not left as a shortcut — the unsafe path ceases to exist.
- **Enforcement = Beforeware + `require()` hybrid.** Beforeware loads `ctx` (user, active team, perms) once;
  each route calls `require(ctx, "perm")`; data access funnels through the scoped helper. A missing
  permission can never widen a result set.
- **IDOR:** path/param ids (`/subscriptions/{id}/edit`) are always loaded via the scoped helper, never by raw id.
- **Trust boundaries:** `/teams/switch` re-verifies membership server-side; `build_ctx` re-validates the
  session's active team every request (membership may have been revoked).
- **Last-super-admin / lock-out guards:** block deleting/demoting the last `super_admin` and removing the
  last `team_admin` of a team. **No self-escalation:** `users.manage` can't raise one's own global role; the
  matrix editor can't grant a permission stronger than the actor holds.
- **Snapshot audit:** never deleted, no FK; permanent-delete snapshots into `audit_log` *before* the row is
  removed (and cascades `price_history`).
- Replace the dev `secret_key` with an env-sourced secret before any real deployment.

---

## 8. Future scalability

- Roles/permissions stored as rows → the matrix can later be opened up to custom roles if needed.
- The `team_id` scoping + indexes generalize to many teams/users; the choke-point helper means new
  features inherit isolation for free.
- Clean package seams (`db/`, `rbac.py`, `routes/`) allow swapping SQLite for Postgres, adding background
  jobs (renewal reminders), and per-team settings without touching route logic.
- Audit is append-only and snapshot-based → ready for compliance export and retention policies.

---

## Package layout (target)

```
main.py                     # thin shim: serve(app)
app/
  main.py                   # fast_app(...) + Beforeware + register all routers
  config.py  styles.py  timeutil.py  cost_utils.py  auth.py  rbac.py  session.py
  db/        connection.py schema.py seed.py subscriptions.py users.py teams.py audit.py  __init__.py(re-exports)
  components/ layout.py widgets.py charts.py forms.py fmt.py  __init__.py(re-exports)
  routes/    auth_routes.py dashboard.py manage.py subscriptions.py audit_routes.py
             users.py teams.py admin.py debug.py  __init__.py(ALL_ROUTERS)
```
Each `routes/*.py` owns an `APIRouter()` (`ar`); `app/main.py` calls `ar.to_app(app)`. Route modules never
import `app.main` (avoids circular imports). `python main.py` and `uvicorn app.main:app` both work.

## Phasing
- **Phase 1** — package split (paths unchanged) · frequency/interval/base_unit rename · real soft-delete · snapshot audit · table wrapping. *Runnable: single-tenant app, same UX, cleaner internals.*
- **Phase 2** — teams/roles/permissions schema + seed · Beforeware enforcement · team scoping of every query · team switcher. *Runnable: multi-tenant, role-enforced.*
- **Phase 3** — role-gated nav · team/member management · deleted-records view (restore/purge) · role-permission matrix UI.
