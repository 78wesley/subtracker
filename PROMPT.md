# AI Prompt: Build a Multi-Tenant Subscription Cost Tracker with Python-FastHTML

## Overview
Build a full-stack subscription management web application using **Python FastHTML**.
It is a production-quality tool for tracking recurring spend, with multi-tenant teams,
role-based access control, period-aware price history, an audit log, and cost analytics.

> This document is the living spec for the project. It started as the original build
> prompt and has been kept in sync as the app evolved. The iterative feedback that
> drove the changes is preserved at the end under **Change history**.

---

## Tech Stack
- **Framework**: Python FastHTML (`python-fasthtml`) — server-rendered, HTMX for dynamic bits.
- **Database**: SQLite via `sqlite-utils` (file-based, WAL mode, created on first boot).
- **Auth**: Session-based login on FastHTML's signed-cookie sessions; passwords hashed with **bcrypt**.
- **Styling**: Tailwind (Play CDN) configured with **shadcn** design tokens; dark mode via a `class` on `<html>`. (No PicoCSS, no JS build step, no SPA framework.)
- **Packaging**: `uv` for dependency management; runs as `python main.py` or `uvicorn app.main:app`.

---

## Architecture

The app is a single FastHTML instance assembled in `app/main.py`, with one `APIRouter`
per feature area registered onto it. A `Beforeware` (`app/session.py`) runs on every
non-public request: it loads the logged-in user, resolves the active team and effective
permissions, and stashes a request **context** (`Ctx`) in the request scope. Routes pull
`ctx` from the scope and guard themselves with `require(ctx, "<permission>")`.

### Multi-tenancy & RBAC
- **Subscriptions are owned by a team**, not a user. Users belong to one or more teams
  and switch between them; the chosen team scopes everything they see and do.
- Two role axes that **compose by union**:
  - **Global role** (`users.global_role`): `super_admin` (runs everything across all
    teams) or the implicit baseline `user`.
  - **Team role** (`team_members.team_role`): `team_admin` (full management of their
    team) or `viewer` (read-only).
- A `super_admin` can enter a cross-team **"view all"** mode that aggregates every team.
- The **role → permission matrix is stored in the database** (`roles`, `permissions`,
  `role_permissions`) and seeded idempotently on boot, so it is editable without code
  changes. Permission *strings* are fixed in code because enforcement references them.

---

## Database Schema

All tables are created idempotently on boot (create-if-absent + add-column-if-absent),
so `init_db()` is safe to call every start. Soft-deletable rows carry
`deleted_at` / `deleted_by` and use partial unique indexes scoped to live (non-deleted) rows.

### Table: `users`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| username | TEXT | Unique among live users |
| password_hash | TEXT | bcrypt |
| global_role | TEXT | `super_admin` or `user` |
| created_at | DATETIME | |
| deleted_at / deleted_by | DATETIME / INTEGER | Soft-delete |

### Table: `teams`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name / slug | TEXT | Slug unique among live teams |
| description | TEXT | |
| created_at / created_by | | |
| deleted_at / deleted_by | | Soft-delete |

### Table: `team_members`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| team_id | INTEGER FK → teams.id | |
| user_id | INTEGER FK → users.id | |
| team_role | TEXT | `team_admin` / `viewer` |
| created_at / created_by, deleted_at / deleted_by | | One live membership per (team, user) |

### Tables: `roles`, `permissions`, `role_permissions`
The DB-driven RBAC matrix. `roles(name, scope, label, is_system, rank)`,
`permissions(name, label, category)`, and the join `role_permissions(role_name, permission_name)`.

### Table: `subscriptions`
Cadence & identity metadata only — the price and active dates live in `subscription_periods`.
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| team_id | INTEGER FK → teams.id | Owning team |
| created_by | INTEGER FK → users.id | |
| name | TEXT | e.g. "Netflix" |
| currency | TEXT | "EUR" (stored, not converted) |
| category | TEXT | Optional grouping label |
| notes | TEXT | Free text |
| frequency | TEXT | `daily` / `weekly` / `monthly` / `quarterly` / `yearly` / `custom` |
| interval | INTEGER | N (only meaningful for `custom`; presets imply 1) |
| base_unit | TEXT | For `custom` only: `daily` / `weekly` / `monthly` / `yearly` |
| created_at / updated_at | DATETIME | |
| deleted_at / deleted_by | | Soft-delete |

### Table: `subscription_periods`
A subscription has one or more **non-overlapping dated windows**, each with its own price.
This replaces the original `start_date`/`end_date`/`amount`/`is_active` columns *and* the
separate `subscription_price_history` table — a price change is just the start of a new period.
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| subscription_id | INTEGER FK → subscriptions.id | |
| amount | DECIMAL | Price during this window |
| start_date | DATE | Window start (inclusive) |
| end_date | DATE | Window end (inclusive); NULL = open-ended/ongoing |
| created_at / created_by | | |

A subscription is **active on a date** when a period contains it; its **current price** is
the amount of the period containing today. There is no `is_active` flag — activity is derived
from the periods and the current date.

### Table: `audit_log`
Intentionally **FK-free and denormalised** so entries outlive the records (and users/teams)
they describe — they must survive permanent deletion.
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| actor_user_id / actor_name / actor_global_role | | Who did it (copied, not joined) |
| team_id / team_name | | Team context |
| action | TEXT | CREATE / UPDATE / DELETE / PRICE_CHANGE / RESTORE / PURGE / LOGIN / LOGOUT … |
| entity_type / entity_id / entity_name | | What was affected |
| old_values / new_values | TEXT | JSON snapshots (changed fields only on UPDATE) |
| description | TEXT | Human-readable summary |
| timestamp | DATETIME | |

---

## Repeat / Frequency & Cost Logic

A cadence is the triple `(frequency, interval, base_unit)`:
- A **named preset** (`daily`/`weekly`/`monthly`/`quarterly`/`yearly`) always means "every 1 unit".
- `custom` means "every `interval` `base_unit`s" — e.g. every 6 months, every 2 weeks.

`resolve()` collapses the triple to an `(effective_unit, n)` pair the math uses. Cost
normalisation goes through a daily cost and multiplies/divides up (see `app/cost_utils.py`):

```python
DAYS_PER_UNIT = {"daily": 1, "weekly": 7, "monthly": 30.4375,
                 "quarterly": 91.3125, "yearly": 365.25}

def get_annual_cost(amount, frequency, interval=1, base_unit=None):
    unit, n = resolve(frequency, interval, base_unit)
    return round(amount * (365.25 / (DAYS_PER_UNIT[unit] * n)), 2)
```

**Period- and price-aware spend.** Because a subscription can have several periods at
different prices, true spend over a window is the sum of each period's prorated daily cost
across the days it overlaps the window:

```python
def range_cost(sub, periods, range_start, range_end):
    total = 0.0
    for p in periods:
        # clip [p.start, p.end] to [range_start, range_end], prorate by overlapping days
        ...
    return round(total, 2)
```

`year_cost`, `monthly_costs_for_year`, and `upcoming_payments_for_periods` build on this.
All "today"/"now" reads go through `app/timeutil.py` (never `date.today()` directly) so the
clock is consistent and mockable in tests.

---

## Application Pages & Routes

Public: `/setup` (first-run), `/login`, `/logout`. Everything else requires a session and
the relevant permission.

### First-run setup — `/setup`
When **no live users exist**, all traffic is funnelled here to create the initial
**super-admin**. No admin is seeded by default.

### Auth — `/login`, `/logout`
Username + password; `LOGIN` / `LOGOUT` written to the audit log.

### Dashboard — `/dashboard?year=YYYY`
Two lenses over the active team (or all teams for a super-admin in view-all mode):
- **Historical** — what the selected **calendar year** actually cost, prorating every
  subscription over its active days and price changes. Headline total with a
  **year-over-year** delta badge, plus per-period cost cards (daily/weekly/monthly/quarterly/yearly).
- **Run-rate** — what is being paid *right now*: subscriptions active today at today's
  price, annualised ("what's my ongoing commitment").
- **Charts** — monthly-spend bar chart for the year, and breakdowns by subscription,
  category, and billing frequency. Year navigation (← previous / next →).

### Manage — `/manage`
The subscriptions table for the active team: name, frequency, current price, next payment,
status. Search/filter, and per-row edit / delete / detail actions. Entry point to import/export.

### Create / Edit subscription — `/manage/new`, `/subscriptions/{id}/edit`
Identity + cadence fields (name, category, frequency/interval/base_unit, notes). Creating a
subscription also creates its first period. Editing identity does **not** alter periods.

### Price periods — `/subscriptions/{id}/periods/add`, `…/periods/{pid}/edit`, `…/periods/{pid}/delete`
Add, edit, or delete a period. Adding a period auto-closes the previous open-ended period the
day before the new one starts. A price change is modelled as a new period (audited as `PRICE_CHANGE`).

### Subscription detail — `/subscriptions/{id}/detail`
All fields, the full **price-period history**, an **upcoming payments** forecast, and a
per-entity audit trail.

### Delete — `/subscriptions/{id}/delete`
**Soft delete** (sets `deleted_at`/`deleted_by`); reversible. Audited as `DELETE`.

### Deleted records (admin) — `/admin/deleted`, `…/restore`, `…/purge`
View soft-deleted records, **restore** them, or **permanently purge** (hard delete) — gated by
`records.*` / `subscriptions.delete.permanent` permissions and audited.

### Teams — `/teams`, `/teams/new`, `/teams/switch`, `/teams/view-all`, `/teams/{id}/members…`
Create teams, switch the active team, toggle a super-admin's view-all mode, and add / remove
members or change their team role.

### Users — `/users`, `/users/new`, `/users/{id}/role`, `/users/{id}/delete`
User management for permitted roles: list, create, change global role, soft-delete. Audited.

### Audit log — `/audit`
The team's audit log, filterable by action, paginated, collapsed by default.

### Import / Export — `/export?fmt=csv|json`, `/import`
Round-trip the active team's subscriptions **and their price periods**. Export needs
`subscriptions.view`; import needs `subscriptions.create` and a specific writable team
(not "all teams"). CSV is one row per period (rows sharing a `name` merge into one
subscription); JSON nests `periods` under each subscription. Imports are size-capped (5 MB) and
row-capped, tolerate a UTF-8 BOM, and neutralise CSV formula injection on both export and import.

---

## Business Rules & Edge Cases

1. **Activity & price are derived, never stored as a flag** — a subscription is active on a
   date iff a period covers it; the current price is the covering period's amount.
2. **Non-overlapping periods** — adding a period auto-closes the prior open-ended one.
3. **Historical dashboard** prorates each period across the days it overlaps the selected year,
   so price changes mid-year are reflected proportionally.
4. **Run-rate** counts only subscriptions active today, at today's price.
5. **Cadence**: `interval ≥ 1` always; named presets force `interval = 1` and no `base_unit`.
6. **Currency** is stored (EUR) but never converted.
7. **Audit `old/new` values** are JSON; UPDATE logs only the fields that changed. The audit log
   is FK-free so it survives permanent deletion.
8. **Tenancy isolation**: users only see the teams they belong to; a super-admin may switch to
   any team or view all at once.
9. **Soft-delete first**: deletes are reversible; only permitted roles can purge permanently.
10. **No default admin**: the first run creates the super-admin via `/setup`.
11. **Central clock**: all date/time reads go through `app/timeutil.py` for consistency and test
    mockability.

---

## Project Layout

```
app/
  main.py            ASGI app assembly + global styles/scripts (Tailwind/shadcn, theme, dropdowns)
  config.py          env-driven configuration (SUBTRACKER_SECRET / _DB / _PORT)
  session.py         auth gate (Beforeware) + request context
  rbac.py / authz.py role catalog, permission resolution, per-route guard
  auth.py            bcrypt hashing + authentication
  cost_utils.py      cadence math, prorated/period-aware cost, next payments
  timeutil.py        central date/time provider
  styles.py          shadcn token CSS + Tailwind utility-class constants
  db/                schema (idempotent + legacy→periods migration), data access per entity, seed
  routes/            one APIRouter per feature area (auth, dashboard, manage, subscriptions,
                     import_export, audit, users, teams, admin)
  components/        FastHTML view helpers (shadcn-styled) + charts + formatting
tests/               pytest suite (cost math, RBAC, auth, migration, HTTP smoke)
main.py              top-level shim → app.main:app
```

---

## Deliverable

Starts with `uv run python main.py`, opens on `http://localhost:5001`, presents the first-run
setup (or login), and is fully functional with the features above. See `README.md` for
configuration and deployment (Docker Compose and Home Assistant add-on).

---

## Change history

The project was built from an initial single-user spec and iterated via feedback. The notable
shifts captured above:

### From the original single-user prompt
- One `users` table owned subscriptions directly; PicoCSS styling; a `subscriptions` table with
  `start_date` / `end_date` / `amount` / `is_active`; a separate `subscription_price_history` table.

### Feedback #1 (drove the current shape)
- Dashboard widgets must show the **whole-year total including price-change differences**, with a
  **year selector**, then split into Daily / Weekly / Monthly / Quarterly.
- Add the ability to **delete a price change** (now: delete a period).
- **Fix CSV export.**
- **Do not create an admin user by default**; add a **`/setup` page** to create the first admin
  when no users exist.
- On the detail page, add a **"Next expected" upcoming-payments list** below the price history;
  **collapse the audit log by default**.
- Refactor toward **less-repetitive code / shared helpers**.
- Add a **global date/time function** (`app/timeutil.py`) used everywhere a clock is needed, so
  the date can be overridden for debugging.

### Subsequent evolution
- Reworked styling from PicoCSS to **Tailwind + shadcn tokens** with dark mode.
- Replaced the `start_date`/`amount`/`is_active` columns and `subscription_price_history` table
  with the unified **`subscription_periods`** model (a one-shot migration backfills legacy data).
- Introduced **multi-tenant teams**, the **DB-driven RBAC** matrix, soft-delete + restore/purge,
  **custom cadences**, **categories**, **JSON import/export**, and the **run-rate** dashboard lens.
