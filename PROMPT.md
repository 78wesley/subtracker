# AI Prompt: Build a Subscription Viewer & Manager Tool with Python-FastHTML

## Overview
Build a full-stack subscription management web application using **Python FastHTML**. This is a production-quality tool for managing recurring subscriptions with multi-user support, audit logging, and cost analytics.

---

## Tech Stack
- **Framework**: Python FastHTML (`python-fasthtml`)
- **Database**: SQLite via `sqlite-utils` or `peewee` ORM (keep it simple, file-based)
- **Auth**: Session-based login using FastHTML's built-in session handling
- **Styling**: PicoCSS (ships with FastHTML) — clean and functional
- **No JavaScript frameworks** — use HTMX (built into FastHTML) for dynamic interactions

---

## Database Schema

### Table: `users`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| username | TEXT | Unique |
| password_hash | TEXT | bcrypt hashed |
| created_at | DATETIME | |

### Table: `subscriptions`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| user_id | INTEGER FK | references users.id |
| name | TEXT | Subscription name (e.g. "Netflix") |
| amount | DECIMAL | Current active amount |
| currency | TEXT | Default: "EUR" |
| start_date | DATE | When subscription started |
| end_date | DATE | Optional, nullable — when it ends/ended |
| notes | TEXT | Free-text notes/remarks |
| repeat_unit | TEXT | One of: daily, weekly, monthly, quarterly, halfyear, yearly |
| repeat_skip | INTEGER | Default: 1 — e.g. 2 = bi-monthly if repeat_unit=monthly |
| is_active | BOOLEAN | True/False |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### Table: `subscription_price_history`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| subscription_id | INTEGER FK | references subscriptions.id |
| amount | DECIMAL | The new price |
| valid_from | DATE | Date from which the new price is active |
| created_at | DATETIME | When this record was added |
| created_by | INTEGER FK | references users.id |

### Table: `audit_log`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| user_id | INTEGER FK | references users.id |
| action | TEXT | e.g. CREATE, UPDATE, DELETE, PRICE_CHANGE, LOGIN, LOGOUT |
| entity_type | TEXT | e.g. subscription, user |
| entity_id | INTEGER | ID of the affected record |
| old_values | TEXT | JSON string of old state (nullable) |
| new_values | TEXT | JSON string of new state (nullable) |
| description | TEXT | Human-readable summary |
| timestamp | DATETIME | When this happened |

---

## Repeat / Frequency Logic

The `repeat_unit` + `repeat_skip` combination defines the billing frequency:

| repeat_unit | repeat_skip | Meaning |
|---|---|---|
| monthly | 1 | Every month |
| monthly | 2 | Every 2 months (bi-monthly) |
| monthly | 3 | Every quarter (alternative) |
| weekly | 2 | Every 2 weeks (bi-weekly) |
| yearly | 1 | Annual |
| quarterly | 1 | Every 3 months |
| halfyear | 1 | Every 6 months |
| daily | 1 | Every day |

**Cost normalization function** — implement this helper to convert any subscription into a daily cost, then multiply up:

```python
def get_annual_cost(amount: float, repeat_unit: str, repeat_skip: int = 1) -> float:
    """Returns the yearly cost of a subscription."""
    days_per_unit = {
        "daily": 1,
        "weekly": 7,
        "monthly": 30.4375,   # average days/month
        "quarterly": 91.3125,
        "halfyear": 182.625,
        "yearly": 365.25,
    }
    days_between_payments = days_per_unit[repeat_unit] * repeat_skip
    payments_per_year = 365.25 / days_between_payments
    return round(amount * payments_per_year, 2)

def get_period_cost(amount: float, repeat_unit: str, repeat_skip: int, period: str) -> float:
    """period: 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'"""
    annual = get_annual_cost(amount, repeat_unit, repeat_skip)
    divisors = {
        "daily": 365.25,
        "weekly": 52.18,
        "monthly": 12,
        "quarterly": 4,
        "yearly": 1,
    }
    return round(annual / divisors[period], 2)
```

For a subscription with a **price history**, always use the record from `subscription_price_history` where `valid_from <= today` ordered by `valid_from DESC LIMIT 1` to get the current active price.

---

## Application Pages & Routes

### 1. `/login` — Login Page
- Username + password form
- On success: redirect to `/dashboard`
- On failure: show error message
- Log `LOGIN` action in audit_log on success

### 2. `/logout`
- Clears session
- Logs `LOGOUT` in audit_log
- Redirects to `/login`

### 3. `/dashboard` — Main Overview (protected)
**Top section: Cost Summary Cards**
Show 5 cards side by side:
- Total Daily cost
- Total Weekly cost
- Total Monthly cost
- Total Quarterly cost
- Total Yearly cost

Only include **active** subscriptions where `end_date IS NULL OR end_date >= today`.
Use the active price from `subscription_price_history` (or `subscriptions.amount` if no history exists yet).
All amounts displayed in EUR.

**Main section: Subscriptions Table**
Columns: Name | Amount | Frequency | Start Date | End Date | Notes | Actions
- Filter bar: search by name, filter by active/inactive/all
- Each row has: Edit button, Delete button (with confirm), Price Change button
- Clicking a row or a "detail" button shows the price history for that subscription

### 4. `/subscriptions/new` — Create Subscription (GET form + POST handler)
Form fields:
- Name (text, required)
- Amount (number, decimal, required)
- Currency (text, default EUR, readonly for now)
- Start Date (date picker, required)
- End Date (date picker, optional)
- Repeat Unit (select: daily / weekly / monthly / quarterly / halfyear / yearly)
- Repeat Skip (number, default 1, min 1)
- Notes (textarea, optional)
- Is Active (checkbox, default checked)

On POST:
1. Insert into `subscriptions`
2. Insert the initial amount into `subscription_price_history` with `valid_from = start_date`
3. Write to `audit_log`: action=CREATE, entity_type=subscription
4. Redirect to `/dashboard`

### 5. `/subscriptions/{id}/edit` — Edit Subscription (GET form + POST handler)
Same fields as create form, pre-filled.
**Important**: Editing `amount` here does NOT update the price history — it updates only the base record. Show a note: "To change the price with a future effective date, use the Price Change button."
On POST:
1. Update `subscriptions` record
2. Write to `audit_log`: action=UPDATE, include old_values and new_values as JSON

### 6. `/subscriptions/{id}/price-change` — Add a Price Change (GET form + POST handler)
Form fields:
- New Amount (decimal, required)
- Valid From (date, required — must be >= today, show warning if backdating)
- Notes (optional, textarea)

On POST:
1. Insert into `subscription_price_history`
2. Update `subscriptions.amount` to the new amount (for convenience)
3. Write to `audit_log`: action=PRICE_CHANGE, include old amount, new amount, valid_from
4. Redirect to `/subscriptions/{id}/detail`

### 7. `/subscriptions/{id}/detail` — Subscription Detail Page
Shows:
- All subscription fields
- Full price history table: Amount | Valid From | Added By | Added At
- Mini audit log for this subscription (filtered from audit_log by entity_id)

### 8. `/subscriptions/{id}/delete` — Delete (POST only, with HTMX confirm)
- Soft delete preferred: set `is_active = False` and `end_date = today` — OR hard delete, your choice, but document it
- Write to `audit_log`: action=DELETE
- Redirect to `/dashboard`

### 9. `/audit` — Audit Log Page (protected)
- Full table of all audit_log entries for the current user
- Columns: Timestamp | Action | Entity | Description | Old Values | New Values
- Pagination (25 per page)
- Filter by action type

### 10. `/users` — User Management (admin-only, optional stretch goal)
- List all users
- Create new user
- Delete user
- Each action logged to audit_log

---

## Business Rules & Edge Cases

1. **Active price resolution**: Always query price history. If no price history exists, fall back to `subscriptions.amount`.
2. **Cost dashboard**: Only include subscriptions where `is_active = True` AND (`end_date IS NULL OR end_date >= date.today()`).
3. **Price change backdating**: Allow it but show a warning in the UI: "This date is in the past. The dashboard will reflect the new amount immediately."
4. **Repeat Skip = 1 is always default**. Never allow 0 or negative.
5. **Currency**: Hardcode EUR for now. Store it in the DB but don't build a converter.
6. **Audit log old/new values**: Serialize as JSON strings. On UPDATE actions, only log fields that actually changed.
7. **Multi-user isolation**: Users only see their own subscriptions. Audit log shows only the current user's actions. Admin users (optional) can see all.
8. **Session security**: Protect all routes except `/login` with a session check. Redirect to `/login` if not authenticated.

---

## File Structure

```
subscription_tool/
├── main.py              # FastHTML app, all routes
├── database.py          # DB init, table creation, helper functions
├── models.py            # Data classes / ORM models
├── auth.py              # Login, logout, session helpers, password hashing
├── cost_utils.py        # get_annual_cost(), get_period_cost() helpers
├── audit.py             # write_audit_log() helper function
├── subscriptions.db     # SQLite database (auto-created)
└── requirements.txt     # python-fasthtml, bcrypt, sqlite-utils (or peewee)
```

---

## Implementation Notes

- Use `python-fasthtml`'s `fast_app()` to bootstrap the app
- Use HTMX `hx-confirm` for delete confirmations (no custom JS needed)
- Use HTMX `hx-get` / `hx-post` for inline form submissions where it makes sense
- Keep all HTML rendering in Python using FastHTML's `Div`, `Table`, `Form`, `Input`, etc. components — no separate template files needed unless you prefer it
- Use `@app.get` and `@app.post` decorators for all routes
- Password hashing: use `bcrypt` library, hash on registration, verify on login
- Date handling: use Python's `datetime.date` and store as ISO strings in SQLite (`YYYY-MM-DD`)
- For the cost summary, compute everything in Python on each dashboard load (no caching needed at this scale)

---

## Stretch Goals (implement if time allows)

1. **Export to CSV**: Button on `/dashboard` to download all active subscriptions as CSV
2. **Next payment date**: Calculate the next billing date based on `start_date`, `repeat_unit`, `repeat_skip`
3. **Upcoming payments widget**: Show subscriptions due in the next 30 days on the dashboard
4. **Dark mode toggle**: Store preference in session
5. **User registration page**: Allow self-signup instead of only admin-created users

---

## Example `requirements.txt`

```
python-fasthtml
bcrypt
sqlite-utils
```

---

## Deliverable

A single working Python application that can be started with:
```bash
pip install -r requirements.txt
python main.py
```

It should open on `http://localhost:5001`, show a login screen, and be fully functional with the above features.



## FEEDACK #1
Looks and works great! but The dashboard widgets shows not the total with the price changes if they are found.

The widgets needs to show the total of the whole year (also add year selection) including price change differences ect then separate it within Daily Weekly Monthly Quarterly.

There is also no option to delete a price change, this needs to be added incase you make a mistake.

The export doesnt to csv doesn't work.

don't create an admin user by default.

If there are no users, there needs to be a setup page to create the admin user.

At the subscriptions detail page there needs to be a Next expected list  below the Price History.
also the audit log needs to be collapsed by default.

Write the python code less repeatable use functions.

There also needs to be a global time date function that is used at places that needs time date.
So i can change the date and time for debug purpose.


