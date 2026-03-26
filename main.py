"""
main.py — SubTracker FastHTML application.

All routes, UI components, and business logic live here.
Shared UI primitives are defined once and reused throughout.
"""

from fasthtml.common import *
from starlette.responses import Response as StarletteResponse
import json
import csv
import io

import timeutil
from database import (
    get_db, init_db, get_user_by_id, has_any_users,
    get_active_price, get_active_subscriptions, get_all_subscriptions,
    get_subscription, get_price_history, delete_price_history_entry,
    get_audit_for_entity, get_audit_log,
)
from auth import authenticate, create_user
from audit import write_audit_log
from cost_utils import (
    REPEAT_UNITS, get_period_cost, get_annual_cost, frequency_label,
    next_payment_date, upcoming_payments, year_cost_with_price_history,
)

# ══════════════════════════════════════════════════════════════════════════════
# App bootstrap
# ══════════════════════════════════════════════════════════════════════════════

CSS = """
:root { --pico-font-size: 15px; }
body  { max-width: 1200px; margin: 0 auto; padding: 1rem; }

/* Nav */
nav { display:flex; align-items:center; gap:1.5rem; padding:0.75rem 1rem;
      background:var(--pico-card-background-color);
      border-radius:var(--pico-border-radius); margin-bottom:1.5rem;
      border:1px solid var(--pico-muted-border-color); }
nav .brand { font-weight:700; font-size:1.1rem; text-decoration:none; color:var(--pico-color); }
nav a      { text-decoration:none; color:var(--pico-muted-color); }
nav a:hover{ color:var(--pico-color); }
nav .spacer{ flex:1; }
nav .debug-pill { background:#fef3c7; border:1px solid #fbbf24; color:#92400e;
                  font-size:0.72rem; padding:0.15rem 0.55rem; border-radius:999px; }

/* Cost cards */
.cost-cards { display:grid; grid-template-columns:repeat(5,1fr); gap:1rem; margin-bottom:1rem; }
.cost-card  { background:var(--pico-card-background-color); border:1px solid var(--pico-muted-border-color);
              border-radius:var(--pico-border-radius); padding:1rem; text-align:center; }
.cost-card .label  { font-size:0.72rem; color:var(--pico-muted-color); text-transform:uppercase;
                     letter-spacing:.05em; margin-bottom:.25rem; }
.cost-card .amount { font-size:1.35rem; font-weight:700; color:var(--pico-primary); }
.cost-card .sub    { font-size:0.75rem; color:var(--pico-muted-color); margin-top:.2rem; }

/* Year selector */
.year-bar { display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem; flex-wrap:wrap; }
.year-bar label { margin:0; font-size:0.85rem; }
.year-bar select, .year-bar input { margin:0; padding:0.3rem 0.6rem; height:auto; }

/* Filters */
.filters { display:flex; gap:1rem; align-items:flex-end; margin-bottom:1rem; flex-wrap:wrap; }
.filters label { margin:0; font-size:0.85rem; }
.filters input, .filters select { margin:0; padding:0.35rem 0.6rem; height:auto; }

/* Tables */
table { font-size:0.9rem; }
th    { white-space:nowrap; }

/* Badges */
.badge          { display:inline-block; padding:.15rem .5rem; border-radius:999px; font-size:.75rem; font-weight:600; }
.badge-active   { background:#d1fae5; color:#065f46; }
.badge-inactive { background:#fee2e2; color:#991b1b; }
.badge-warn     { background:#fef3c7; color:#92400e; }
.badge-info     { background:#dbeafe; color:#1e40af; }

/* Action buttons */
.action-btns { display:flex; gap:.4rem; white-space:nowrap; }
.action-btns button, .action-btns a { padding:.25rem .6rem; font-size:.8rem; margin:0; }

/* Layout */
.page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1.25rem; }
.page-header h2 { margin:0; }

/* Alerts */
.alert-warning { background:#fef3c7; border:1px solid #fbbf24; color:#92400e;
                 padding:.75rem 1rem; border-radius:var(--pico-border-radius); margin-bottom:1rem; }
.alert-error   { background:#fee2e2; border:1px solid #f87171; color:#991b1b;
                 padding:.75rem 1rem; border-radius:var(--pico-border-radius); margin-bottom:1rem; }
.alert-success { background:#d1fae5; border:1px solid #6ee7b7; color:#065f46;
                 padding:.75rem 1rem; border-radius:var(--pico-border-radius); margin-bottom:1rem; }

/* Section cards */
.section-card    { background:var(--pico-card-background-color); border:1px solid var(--pico-muted-border-color);
                   border-radius:var(--pico-border-radius); padding:1.25rem; margin-bottom:1.25rem; }
.section-card h3 { margin-top:0; font-size:1rem; }

/* Collapsible */
details summary { cursor:pointer; font-weight:600; font-size:1rem; margin-bottom:.5rem; }
details[open] summary { margin-bottom:1rem; }

/* Upcoming */
.upcoming-item { display:flex; justify-content:space-between; align-items:center;
                 padding:.4rem 0; border-bottom:1px solid var(--pico-muted-border-color); }
.upcoming-item:last-child { border-bottom:none; }

pre { font-size:.78rem; white-space:pre-wrap; word-break:break-all; }
"""

app, rt = fast_app(
    secret_key="sub-manager-secret-key-change-in-prod",
    hdrs=(Style(CSS),),
)

# ══════════════════════════════════════════════════════════════════════════════
# UI primitives  (define once, reuse everywhere)
# ══════════════════════════════════════════════════════════════════════════════

def nav_bar(username: str) -> Nav:
    debug = timeutil.get_debug_date()
    debug_pill = Span(f"🕐 Debug date: {debug}", cls="debug-pill") if debug else ""
    return Nav(
        A("💳 SubTracker", href="/dashboard", cls="brand"),
        A("Dashboard", href="/dashboard"),
        A("Audit Log", href="/audit"),
        A("Users", href="/users"),
        A("Debug", href="/debug"),
        debug_pill,
        Div(cls="spacer"),
        Span(f"👤 {username}", style="color:var(--pico-muted-color); font-size:.85rem;"),
        A("Logout", href="/logout"),
    )


def page_title(title: str) -> Title:
    return Title(f"{title} – SubTracker")


def alert(msg: str, kind: str = "warning") -> Div:
    return Div(msg, cls=f"alert-{kind}")


def badge(text: str, kind: str = "active") -> Span:
    return Span(text, cls=f"badge badge-{kind}")


def action_btn(label: str, href: str = None, cls: str = "secondary outline",
               hx_post: str = None, hx_confirm: str = None) -> object:
    """Return a small action button, either a link or an HTMX button."""
    btn = Button(label, cls=cls, style="padding:.25rem .6rem; font-size:.8rem; margin:0;")
    if href:
        return A(btn, href=href)
    if hx_post:
        btn.attrs["hx-post"] = hx_post
        btn.attrs["hx-target"] = "body"
        btn.attrs["hx-push-url"] = "true"
        if hx_confirm:
            btn.attrs["hx-confirm"] = hx_confirm
        return btn
    return btn


def section_card(*children, heading: str = None) -> Div:
    inner = [H3(heading)] if heading else []
    inner += list(children)
    return Div(*inner, cls="section-card")


def collapsible_card(heading: str, *children, open_: bool = False) -> Details:
    return Details(
        Summary(heading),
        *children,
        cls="section-card",
        **({"open": True} if open_ else {}),
    )


def status_badge(is_active: int) -> Span:
    return badge("Active", "active") if is_active else badge("Inactive", "inactive")


def fmt_eur(amount: float) -> str:
    return f"€{amount:,.2f}"


def truncate(text: str, n: int = 45) -> str:
    t = text or ""
    return t[:n] + "…" if len(t) > n else t


def pagination_bar(page: int, total_pages: int, base_url: str) -> Div:
    sep = "&" if "?" in base_url else "?"
    prev_btn = A(Button("← Prev", cls="secondary outline"),
                 href=f"{base_url}{sep}page={page-1}") if page > 1 else ""
    next_btn = A(Button("Next →", cls="secondary outline"),
                 href=f"{base_url}{sep}page={page+1}") if page < total_pages else ""
    return Div(prev_btn,
               Span(f" Page {page} of {total_pages} ", style="padding:0 .75rem"),
               next_btn,
               style="display:flex; align-items:center; margin-top:1rem;")


def json_pretty(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2) if raw else ""
    except Exception:
        return raw or ""


# ══════════════════════════════════════════════════════════════════════════════
# Session helpers
# ══════════════════════════════════════════════════════════════════════════════

def current_user(session: dict):
    uid = session.get("user_id")
    return get_user_by_id(get_db(), uid) if uid else None


def require_login(session: dict):
    """Return a redirect if not logged in, else None."""
    if not session.get("user_id"):
        return RedirectResponse("/login", status_code=303)
    return None


def guard(session: dict):
    """Combined guard: redirects to setup if no users, login if not authenticated."""
    db = init_db()
    if not has_any_users(db):
        return RedirectResponse("/setup", status_code=303)
    return require_login(session)


# ══════════════════════════════════════════════════════════════════════════════
# Setup (first-run: create admin)
# ══════════════════════════════════════════════════════════════════════════════

@rt("/setup")
def get(session, error: str = ""):
    db = init_db()
    if has_any_users(db):
        return RedirectResponse("/login", status_code=303)
    return page_title("Setup"), Titled("Welcome to SubTracker",
        Card(
            H2("Create your admin account", style="margin-top:0"),
            alert(error, "error") if error else "",
            P("No users exist yet. Create the first account to get started."),
            Form(
                Label("Username", Input(name="username", required=True,
                      placeholder="admin", autofocus=True)),
                Label("Password", Input(type="password", name="password",
                      required=True, placeholder="choose a password")),
                Label("Confirm Password", Input(type="password", name="password2",
                      required=True, placeholder="repeat password")),
                Button("Create Account", type="submit", style="width:100%"),
                method="post", action="/setup",
            ),
            style="max-width:400px; margin:4rem auto;",
        )
    )


@rt("/setup")
async def post(session, username: str, password: str, password2: str):
    db = init_db()
    if has_any_users(db):
        return RedirectResponse("/login", status_code=303)
    if not username.strip():
        return RedirectResponse("/setup?error=Username+cannot+be+empty", status_code=303)
    if password != password2:
        return RedirectResponse("/setup?error=Passwords+do+not+match", status_code=303)
    if len(password) < 6:
        return RedirectResponse("/setup?error=Password+must+be+at+least+6+characters", status_code=303)
    uid = create_user(username.strip(), password)
    write_audit_log(uid, "CREATE", "user", uid, f"Admin account '{username}' created during setup")
    session["user_id"] = uid
    return RedirectResponse("/dashboard", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Login / Logout
# ══════════════════════════════════════════════════════════════════════════════

@rt("/")
def get(session):
    return RedirectResponse("/dashboard", status_code=303)


@rt("/login")
def get(session, error: str = ""):
    db = init_db()
    if not has_any_users(db):
        return RedirectResponse("/setup", status_code=303)
    return page_title("Login"), Titled("SubTracker",
        Card(
            H2("Sign In", style="margin-top:0"),
            alert(error, "error") if error else "",
            Form(
                Label("Username", Input(name="username", required=True,
                      placeholder="username", autofocus=True)),
                Label("Password", Input(type="password", name="password",
                      required=True, placeholder="password")),
                Button("Sign In", type="submit", style="width:100%"),
                method="post", action="/login",
            ),
            style="max-width:380px; margin:4rem auto;",
        )
    )


@rt("/login")
async def post(session, username: str, password: str):
    user = authenticate(username, password)
    if not user:
        return RedirectResponse("/login?error=Invalid+username+or+password", status_code=303)
    session["user_id"] = user["id"]
    write_audit_log(user["id"], "LOGIN", "user", user["id"], f"User '{username}' logged in")
    return RedirectResponse("/dashboard", status_code=303)


@rt("/logout")
def get(session):
    uid = session.get("user_id")
    if uid:
        u = get_user_by_id(get_db(), uid)
        if u:
            write_audit_log(uid, "LOGOUT", "user", uid, f"User '{u['username']}' logged out")
    session.clear()
    return RedirectResponse("/login", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════

def _build_cost_cards(db, user_id: int, year: int) -> tuple:
    """
    Returns (cost_cards_element, yearly_total).
    Calculates true yearly cost using price history for the selected year,
    then derives period costs from it.
    """
    active = get_active_subscriptions(db, user_id)
    yearly_total = 0.0

    for s in active:
        history = get_price_history(db, s["id"])
        yearly_total += year_cost_with_price_history(s, history, year)

    # From yearly we can derive all other periods
    period_costs = {
        "daily":     round(yearly_total / 365.25, 2),
        "weekly":    round(yearly_total / 52.18,  2),
        "monthly":   round(yearly_total / 12,     2),
        "quarterly": round(yearly_total / 4,      2),
        "yearly":    round(yearly_total,           2),
    }

    cards = Div(
        *[Div(
            Div(p.capitalize(), cls="label"),
            Div(fmt_eur(period_costs[p]), cls="amount"),
            Div(f"{year} total ÷ {p}", cls="sub"),
            cls="cost-card",
        ) for p in ["daily", "weekly", "monthly", "quarterly", "yearly"]],
        cls="cost-cards",
    )
    return cards, yearly_total


@rt("/dashboard")
def get(session, q: str = "", status: str = "all", year: int = None):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()

    current_year = timeutil.today().year
    year = year or current_year
    year_range = list(range(current_year - 3, current_year + 3))

    cost_cards, yearly_total = _build_cost_cards(db, user["id"], year)

    year_bar = Form(
        Div(
            Label("Year", Select(
                *[Option(str(y), value=str(y), selected=(y == year)) for y in year_range],
                name="year",
                onchange="this.form.submit()",
                style="width:100px",
            )),
            Span(f"Total {year}: ", Strong(fmt_eur(yearly_total)),
                 style="align-self:center; color:var(--pico-muted-color); font-size:.9rem;"),
            # Preserve other filters
            Input(type="hidden", name="q", value=q),
            Input(type="hidden", name="status", value=status),
            cls="year-bar",
        ),
        method="get", action="/dashboard",
    )

    # Subscription table
    subs = get_all_subscriptions(db, user["id"],
                                 filter_active=status if status != "all" else None,
                                 search=q or None)
    rows = []
    for s in subs:
        price = get_active_price(db, s["id"], s["amount"])
        rows.append(Tr(
            Td(A(s["name"], href=f"/subscriptions/{s['id']}/detail")),
            Td(fmt_eur(price)),
            Td(frequency_label(s["repeat_unit"], s["repeat_skip"] or 1)),
            Td(s["start_date"] or "—"),
            Td(s["end_date"] or "—"),
            Td(status_badge(s["is_active"])),
            Td(truncate(s["notes"])),
            Td(Div(
                action_btn("✏️ Edit", href=f"/subscriptions/{s['id']}/edit"),
                action_btn("💰 Price", href=f"/subscriptions/{s['id']}/price-change"),
                action_btn("🗑️ Delete",
                           hx_post=f"/subscriptions/{s['id']}/delete",
                           hx_confirm=f"Delete '{s['name']}'? (soft-delete)"),
                cls="action-btns",
            )),
        ))

    table = (
        Table(
            Thead(Tr(Th("Name"), Th("Amount"), Th("Frequency"), Th("Start"),
                     Th("End"), Th("Status"), Th("Notes"), Th("Actions"))),
            Tbody(*rows),
        ) if rows else P("No subscriptions found. ", A("Add one →", href="/subscriptions/new"))
    )

    filter_bar = Form(
        Div(
            Label("Search", Input(name="q", value=q, placeholder="Search name…",
                                  style="width:200px")),
            Label("Status", Select(
                Option("All",      value="all",      selected=(status == "all")),
                Option("Active",   value="active",   selected=(status == "active")),
                Option("Inactive", value="inactive", selected=(status == "inactive")),
                name="status", style="width:130px",
            )),
            Input(type="hidden", name="year", value=str(year)),
            Button("Filter", type="submit",
                   style="margin-bottom:0; padding:.4rem 1rem"),
            A(Button("＋ Add", style="margin-bottom:0; padding:.4rem 1rem"),
              href="/subscriptions/new"),
            A(Button("⬇ CSV", cls="secondary outline",
                     style="margin-bottom:0; padding:.4rem 1rem"),
              href="/subscriptions/export"),
            cls="filters",
        ),
        method="get", action="/dashboard",
    )

    return page_title("Dashboard"), nav_bar(user["username"]), Main(
        Div(H2("Dashboard"), cls="page-header"),
        year_bar,
        cost_cards,
        filter_bar,
        table,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Subscription form (shared between new & edit)
# ══════════════════════════════════════════════════════════════════════════════

def subscription_form(action_url: str, sub: dict = None, btn_label: str = "Save") -> Form:
    s = sub or {}
    today_val = timeutil.today_iso()
    return Form(
        Grid(
            Label("Name *", Input(name="name", value=s.get("name", ""),
                  required=True, placeholder="e.g. Netflix")),
            Label("Amount (€) *", Input(name="amount", type="number", step="0.01",
                  min="0", value=s.get("amount", ""), required=True)),
        ),
        Grid(
            Label("Start Date *", Input(name="start_date", type="date",
                  value=s.get("start_date", today_val), required=True)),
            Label("End Date", Input(name="end_date", type="date",
                  value=s.get("end_date") or "")),
        ),
        Grid(
            Label("Repeat Unit", Select(
                *[Option(u.capitalize(), value=u,
                         selected=(s.get("repeat_unit", "monthly") == u))
                  for u in REPEAT_UNITS],
                name="repeat_unit",
            )),
            Label("Repeat Every (skip)",
                  Input(name="repeat_skip", type="number", min="1",
                        value=s.get("repeat_skip", 1), required=True)),
        ),
        Label("Notes", Textarea(s.get("notes") or "", name="notes", rows=3,
              placeholder="Optional notes…")),
        Label(
            Input(type="checkbox", name="is_active", value="1",
                  checked=(s.get("is_active", 1) in (1, True, "1"))),
            " Active subscription",
        ),
        Button(btn_label, type="submit"),
        method="post", action=action_url,
    )


# ══════════════════════════════════════════════════════════════════════════════
# New subscription
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/new")
def get(session):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    return page_title("New Subscription"), nav_bar(user["username"]), Main(
        Div(H2("Add Subscription"), A("← Dashboard", href="/dashboard"), cls="page-header"),
        subscription_form("/subscriptions/new", btn_label="Create Subscription"),
    )


@rt("/subscriptions/new")
async def post(session, name: str, amount: float, start_date: str,
               end_date: str = "", repeat_unit: str = "monthly",
               repeat_skip: int = 1, notes: str = "", is_active: str = ""):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    now = timeutil.now_iso()
    skip = max(1, repeat_skip)
    is_active_val = 1 if is_active == "1" else 0

    sub_id = db["subscriptions"].insert({
        "user_id": user["id"], "name": name, "amount": amount, "currency": "EUR",
        "start_date": start_date, "end_date": end_date or None, "notes": notes,
        "repeat_unit": repeat_unit, "repeat_skip": skip, "is_active": is_active_val,
        "created_at": now, "updated_at": now,
    }).last_pk

    db["subscription_price_history"].insert({
        "subscription_id": sub_id, "amount": amount, "valid_from": start_date,
        "created_at": now, "created_by": user["id"],
    })

    write_audit_log(user["id"], "CREATE", "subscription", sub_id,
                    f"Created '{name}' €{amount}/{repeat_unit}",
                    new_values={"name": name, "amount": amount,
                                "repeat_unit": repeat_unit, "repeat_skip": skip,
                                "start_date": start_date})
    return RedirectResponse("/dashboard", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Edit subscription
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/{sub_id}/edit")
def get(session, sub_id: int):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)
    return page_title(f"Edit {sub['name']}"), nav_bar(user["username"]), Main(
        Div(H2(f"Edit: {sub['name']}"),
            A("← Back", href=f"/subscriptions/{sub_id}/detail"),
            cls="page-header"),
        alert("Editing amount here updates the base record only. "
              "Use 💰 Price Change to record a dated price change.", "warning"),
        subscription_form(f"/subscriptions/{sub_id}/edit", sub=sub,
                          btn_label="Update Subscription"),
    )


@rt("/subscriptions/{sub_id}/edit")
async def post(session, sub_id: int, name: str, amount: float, start_date: str,
               end_date: str = "", repeat_unit: str = "monthly",
               repeat_skip: int = 1, notes: str = "", is_active: str = ""):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)

    skip = max(1, repeat_skip)
    is_active_val = 1 if is_active == "1" else 0
    old = {k: sub[k] for k in ["name","amount","start_date","end_date",
                                 "repeat_unit","repeat_skip","notes","is_active"]}
    new_vals = {"name": name, "amount": amount, "start_date": start_date,
                "end_date": end_date or None, "repeat_unit": repeat_unit,
                "repeat_skip": skip, "notes": notes, "is_active": is_active_val}
    changed = {k: v for k, v in new_vals.items() if str(v) != str(old.get(k, ""))}

    db["subscriptions"].update(sub_id, {**new_vals, "updated_at": timeutil.now_iso()})
    write_audit_log(user["id"], "UPDATE", "subscription", sub_id,
                    f"Updated '{name}'",
                    old_values={k: old[k] for k in changed},
                    new_values=changed)
    return RedirectResponse(f"/subscriptions/{sub_id}/detail", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Price change
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/{sub_id}/price-change")
def get(session, sub_id: int):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)

    current_price = get_active_price(db, sub_id, sub["amount"])
    return page_title(f"Price Change – {sub['name']}"), nav_bar(user["username"]), Main(
        Div(H2(f"Price Change: {sub['name']}"),
            A("← Back", href=f"/subscriptions/{sub_id}/detail"),
            cls="page-header"),
        P("Current active price: ", Strong(fmt_eur(current_price))),
        Form(
            Label("New Amount (€) *",
                  Input(name="new_amount", type="number", step="0.01",
                        min="0", required=True, placeholder="e.g. 12.99")),
            Label("Valid From *",
                  Input(name="valid_from", type="date",
                        value=timeutil.today_iso(), required=True)),
            Label("Notes", Textarea("", name="notes", rows=2,
                  placeholder="Optional reason for price change…")),
            Button("Save Price Change", type="submit"),
            method="post", action=f"/subscriptions/{sub_id}/price-change",
        ),
    )


@rt("/subscriptions/{sub_id}/price-change")
async def post(session, sub_id: int, new_amount: float, valid_from: str, notes: str = ""):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)

    old_amount = get_active_price(db, sub_id, sub["amount"])
    now = timeutil.now_iso()
    is_past = valid_from < timeutil.today_iso()

    db["subscription_price_history"].insert({
        "subscription_id": sub_id, "amount": new_amount,
        "valid_from": valid_from, "created_at": now, "created_by": user["id"],
    })
    db["subscriptions"].update(sub_id, {"amount": new_amount, "updated_at": now})

    desc = f"Price change '{sub['name']}': {fmt_eur(old_amount)} → {fmt_eur(new_amount)}, effective {valid_from}"
    if is_past:
        desc += " (backdated)"
    if notes:
        desc += f". {notes}"
    write_audit_log(user["id"], "PRICE_CHANGE", "subscription", sub_id, desc,
                    old_values={"amount": old_amount},
                    new_values={"amount": new_amount, "valid_from": valid_from, "notes": notes})
    return RedirectResponse(f"/subscriptions/{sub_id}/detail", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Delete price history entry
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/{sub_id}/price-history/{entry_id}/delete")
async def post(session, sub_id: int, entry_id: int):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)

    # Fetch the entry before deleting for audit
    entries = list(db["subscription_price_history"].rows_where(
        "id = ? AND subscription_id = ?", [entry_id, sub_id]))
    if not entries:
        return RedirectResponse(f"/subscriptions/{sub_id}/detail", status_code=303)

    entry = entries[0]
    delete_price_history_entry(db, entry_id, sub_id)

    # Recalculate the current "active" amount and sync back to subscriptions.amount
    new_active = get_active_price(db, sub_id, sub["amount"])
    db["subscriptions"].update(sub_id, {"amount": new_active, "updated_at": timeutil.now_iso()})

    write_audit_log(user["id"], "DELETE", "subscription_price_history", entry_id,
                    f"Deleted price history entry for '{sub['name']}': "
                    f"{fmt_eur(entry['amount'])} (valid from {entry['valid_from']})",
                    old_values={"amount": entry["amount"], "valid_from": entry["valid_from"]})
    return RedirectResponse(f"/subscriptions/{sub_id}/detail", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Subscription detail
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/{sub_id}/detail")
def get(session, sub_id: int):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)

    today = timeutil.today()
    active_price = get_active_price(db, sub_id, sub["amount"])
    history = get_price_history(db, sub_id)
    audit_entries = get_audit_for_entity(db, sub_id, "subscription")

    # ── Info card ──────────────────────────────────────────────────────────────
    info = section_card(
        H3(sub["name"]),
        Grid(
            Div(P(Small("Amount")),     P(Strong(fmt_eur(active_price)))),
            Div(P(Small("Frequency")),  P(frequency_label(sub["repeat_unit"], sub["repeat_skip"] or 1))),
            Div(P(Small("Start Date")), P(sub["start_date"] or "—")),
            Div(P(Small("End Date")),   P(sub["end_date"] or "—")),
            Div(P(Small("Status")),     P(status_badge(sub["is_active"]))),
            Div(P(Small("Currency")),   P(sub["currency"] or "EUR")),
        ),
        P(Small("Notes"), Br(), sub["notes"] or "—"),
        Div(
            action_btn("✏️ Edit", href=f"/subscriptions/{sub_id}/edit"),
            action_btn("💰 Add Price Change", href=f"/subscriptions/{sub_id}/price-change"),
            cls="action-btns", style="margin-top:.5rem",
        ),
    )

    # ── Cost breakdown card ────────────────────────────────────────────────────
    costs = section_card(
        heading="Cost Breakdown (active price)",
        *[Table(
            Thead(Tr(*[Th(p.capitalize())
                       for p in ["daily","weekly","monthly","quarterly","yearly"]])),
            Tbody(Tr(*[Td(fmt_eur(get_period_cost(
                              active_price, sub["repeat_unit"], sub["repeat_skip"] or 1, p)))
                       for p in ["daily","weekly","monthly","quarterly","yearly"]])),
        )],
    )

    # ── Price history card ─────────────────────────────────────────────────────
    price_rows = [
        Tr(
            Td(fmt_eur(h["amount"])),
            Td(h["valid_from"]),
            Td(h.get("username") or "—"),
            Td(h["created_at"][:16]),
            Td(Form(
                Button("🗑️ Delete", cls="secondary outline",
                       style="padding:.2rem .5rem; font-size:.78rem; margin:0",
                       hx_post=f"/subscriptions/{sub_id}/price-history/{h['id']}/delete",
                       hx_confirm=f"Delete price entry {fmt_eur(h['amount'])} from {h['valid_from']}?",
                       hx_target="body", hx_push_url="true"),
                method="post",
            )),
        )
        for h in history
    ]
    price_hist = section_card(
        heading="Price History",
        *([Table(
            Thead(Tr(Th("Amount"), Th("Valid From"), Th("Added By"), Th("Added At"), Th(""))),
            Tbody(*price_rows),
        )] if price_rows else [P("No price history yet.")]),
    )

    # ── Next expected payments ─────────────────────────────────────────────────
    upcoming = []
    if sub.get("start_date") and sub["is_active"]:
        # Show next 6 billing dates
        d = next_payment_date(sub["start_date"], sub["repeat_unit"], sub["repeat_skip"] or 1, today)
        for _ in range(6):
            price_on_day = get_active_price(db, sub_id, sub["amount"], d.isoformat())
            days_from_now = (d - today).days
            label = "today" if days_from_now == 0 else (
                f"in {days_from_now} day{'s' if days_from_now != 1 else ''}"
                if days_from_now > 0 else f"{-days_from_now}d ago"
            )
            upcoming.append(Div(
                Span(d.isoformat()),
                Span(Span(label, style="color:var(--pico-muted-color); font-size:.8rem; margin-right:.5rem"),
                     Strong(fmt_eur(price_on_day))),
                cls="upcoming-item",
            ))
            d = next_payment_date(sub["start_date"], sub["repeat_unit"], sub["repeat_skip"] or 1,
                                  d + timedelta(days=1))

    next_payments = section_card(
        heading="Next Expected Payments",
        *(upcoming if upcoming else [P("Subscription is inactive or has no start date.")]),
    )

    # ── Audit log (collapsed by default) ──────────────────────────────────────
    audit_rows = [
        Tr(Td(a["timestamp"][:16]), Td(a["action"]), Td(a["description"]))
        for a in audit_entries
    ]
    audit_section = collapsible_card(
        f"Audit Log ({len(audit_entries)} entries)",
        Table(
            Thead(Tr(Th("Time"), Th("Action"), Th("Description"))),
            Tbody(*audit_rows),
        ) if audit_rows else P("No audit entries."),
    )

    return page_title(sub["name"]), nav_bar(user["username"]), Main(
        Div(H2(sub["name"]), A("← Dashboard", href="/dashboard"), cls="page-header"),
        info, costs, price_hist, next_payments, audit_section,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Delete subscription (soft)
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/{sub_id}/delete")
async def post(session, sub_id: int):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    sub = get_subscription(db, sub_id, user["id"])
    if not sub:
        return RedirectResponse("/dashboard", status_code=303)

    db["subscriptions"].update(sub_id, {
        "is_active": 0,
        "end_date":  timeutil.today_iso(),
        "updated_at": timeutil.now_iso(),
    })
    write_audit_log(user["id"], "DELETE", "subscription", sub_id,
                    f"Soft-deleted '{sub['name']}'",
                    old_values={"is_active": sub["is_active"]},
                    new_values={"is_active": 0, "end_date": timeutil.today_iso()})
    return RedirectResponse("/dashboard", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# CSV export
# ══════════════════════════════════════════════════════════════════════════════

@rt("/subscriptions/export")
def get(session):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    subs = get_all_subscriptions(db, user["id"])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID","Name","Active Price (€)","Currency","Frequency",
                "Start Date","End Date","Active","Notes","Annual Cost (€)"])
    for s in subs:
        price = get_active_price(db, s["id"], s["amount"])
        annual = get_annual_cost(price, s["repeat_unit"], s["repeat_skip"] or 1)
        w.writerow([
            s["id"], s["name"], f"{price:.2f}", s["currency"] or "EUR",
            frequency_label(s["repeat_unit"], s["repeat_skip"] or 1),
            s["start_date"] or "", s["end_date"] or "",
            "Yes" if s["is_active"] else "No",
            s["notes"] or "", f"{annual:.2f}",
        ])

    return StarletteResponse(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=subscriptions.csv"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# Audit log page
# ══════════════════════════════════════════════════════════════════════════════

@rt("/audit")
def get(session, action_filter: str = "", page: int = 1):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()

    entries, total = get_audit_log(db, user["id"],
                                   action_filter=action_filter or None, page=page)
    total_pages = max(1, (total + 24) // 25)
    actions = ["LOGIN","LOGOUT","CREATE","UPDATE","DELETE","PRICE_CHANGE"]

    filter_bar = Form(
        Div(
            Label("Action", Select(
                Option("All Actions", value=""),
                *[Option(a, value=a, selected=(action_filter == a)) for a in actions],
                name="action_filter",
            )),
            Button("Filter", type="submit",
                   style="margin-bottom:0; padding:.4rem 1rem"),
            cls="filters",
        ),
        method="get", action="/audit",
    )

    rows = [
        Tr(
            Td(e["timestamp"][:16]),
            Td(badge(e["action"], "active")),
            Td(e["entity_type"]),
            Td(e["description"]),
            Td(Pre(json_pretty(e["old_values"])) if e["old_values"] else "—"),
            Td(Pre(json_pretty(e["new_values"])) if e["new_values"] else "—"),
        )
        for e in entries
    ]

    return page_title("Audit Log"), nav_bar(user["username"]), Main(
        Div(H2("Audit Log"), cls="page-header"),
        filter_bar,
        Table(
            Thead(Tr(Th("Time"), Th("Action"), Th("Entity"),
                     Th("Description"), Th("Old"), Th("New"))),
            Tbody(*rows),
        ) if rows else P("No audit entries found."),
        pagination_bar(page, total_pages, f"/audit?action_filter={action_filter}"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# User management
# ══════════════════════════════════════════════════════════════════════════════

@rt("/users")
def get(session, msg: str = "", msg_kind: str = "warning"):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    all_users = list(db["users"].rows)

    rows = [
        Tr(
            Td(u["id"]),
            Td(u["username"]),
            Td(u["created_at"][:16] if u["created_at"] else "—"),
            Td(
                Form(
                    Button("🗑️ Delete", cls="secondary outline",
                           style="padding:.25rem .6rem; font-size:.8rem; margin:0",
                           hx_post=f"/users/{u['id']}/delete",
                           hx_confirm=f"Delete user '{u['username']}'?",
                           hx_target="body", hx_push_url="/users"),
                    method="post",
                ) if u["id"] != user["id"] else Span("(you)", style="color:var(--pico-muted-color)")
            ),
        )
        for u in all_users
    ]

    return page_title("Users"), nav_bar(user["username"]), Main(
        Div(H2("User Management"), cls="page-header"),
        alert(msg, msg_kind) if msg else "",
        Table(
            Thead(Tr(Th("ID"), Th("Username"), Th("Created"), Th("Actions"))),
            Tbody(*rows),
        ),
        H3("Create New User", style="margin-top:1.5rem"),
        Form(
            Grid(
                Label("Username *", Input(name="username", required=True, placeholder="username")),
                Label("Password *", Input(name="password", type="password",
                      required=True, placeholder="password")),
            ),
            Button("Create User", type="submit"),
            method="post", action="/users/new",
        ),
    )


@rt("/users/new")
async def post(session, username: str, password: str):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    if list(db["users"].rows_where("username = ?", [username])):
        return RedirectResponse("/users?msg=Username+already+exists", status_code=303)
    uid = create_user(username, password)
    write_audit_log(user["id"], "CREATE", "user", uid,
                    f"Admin created user '{username}'",
                    new_values={"username": username})
    return RedirectResponse("/users", status_code=303)


@rt("/users/{uid}/delete")
async def post(session, uid: int):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    db = get_db()
    if uid == user["id"]:
        return RedirectResponse("/users?msg=Cannot+delete+yourself", status_code=303)
    target = get_user_by_id(db, uid)
    if target:
        db["users"].delete(uid)
        write_audit_log(user["id"], "DELETE", "user", uid,
                        f"Deleted user '{target['username']}'")
    return RedirectResponse("/users", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Debug page (date/time override)
# ══════════════════════════════════════════════════════════════════════════════

@rt("/debug")
def get(session, msg: str = ""):
    redir = guard(session)
    if redir: return redir
    user = current_user(session)
    debug = timeutil.get_debug_date()
    return page_title("Debug"), nav_bar(user["username"]), Main(
        Div(H2("Debug Tools"), cls="page-header"),
        Div(
            H3("Date Override"),
            P("Override the application date for testing. All cost calculations, "
              "next-payment dates, and timestamps will use this date."),
            P(Strong("Current effective date: "),
              Span(debug or timeutil.today_iso(), style="font-family:monospace"),
              Span(" (overridden)", cls="badge badge-warn") if debug else
              Span(" (real clock)", cls="badge badge-info")),
            Form(
                Label("Set Debug Date",
                      Input(name="debug_date", type="date",
                            value=debug or timeutil.today_iso())),
                Button("Set Date", type="submit"),
                method="post", action="/debug/set-date",
            ),
            Form(
                Button("Reset to Real Clock", cls="secondary outline", type="submit"),
                method="post", action="/debug/clear-date",
            ) if debug else "",
            alert(msg, "success") if msg else "",
            cls="section-card",
        ),
    )


@rt("/debug/set-date")
async def post(session, debug_date: str):
    redir = guard(session)
    if redir: return redir
    timeutil.set_debug_date(debug_date)
    return RedirectResponse(f"/debug?msg=Date+set+to+{debug_date}", status_code=303)


@rt("/debug/clear-date")
async def post(session):
    redir = guard(session)
    if redir: return redir
    timeutil.set_debug_date(None)
    return RedirectResponse("/debug?msg=Date+reset+to+real+clock", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

from datetime import timedelta  # used in detail page upcoming payments

if __name__ == "__main__":
    init_db()
    print("SubTracker starting on http://localhost:5001")
    print("No default user created — visit /setup on first run.")
    serve(port=5001)
