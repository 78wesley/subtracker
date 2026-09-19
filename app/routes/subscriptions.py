"""
subscriptions.py — Create / edit / period management / detail / soft-delete.

A subscription carries identity + cadence; its dated active windows and prices live
in subscription_periods (multiple, non-overlapping). "Active" and "current price"
are derived from those periods. All reads go through the team-scoped
get_subscription(db, ctx, ...); all writes are gated by require(ctx, ...) and audited.
"""

import calendar
from datetime import date
from urllib.parse import quote_plus

from fasthtml.common import *

from app import timeutil
from app.authz import require, writable_team
from app.components import (
    MONTH_LABELS,
    alert,
    badge,
    bar_chart,
    category_label,
    fmt_eur,
    nav_bar,
    page_title,
    section_card,
    status_badge,
    subscription_form,
    tab_nav,
)
from app.cost_utils import (
    frequency_label,
    get_period_cost,
    monthly_costs_for_year,
    normalise_cadence,
    range_cost,
    upcoming_payments_for_periods,
    year_cost,
)
from app.db import (
    add_period,
    audit,
    current_price,
    delete_period,
    get_audit_for_entity,
    get_categories,
    get_db,
    get_periods,
    get_subscription,
    is_active_on,
    update_period,
    validate_periods,
)
from app.permissions import Perm
from app.styles import (
    CHARTS_GRID,
    COST_AMOUNT,
    COST_CARD,
    COST_LABEL,
    INPUT,
    LINK,
    MUTED_SM,
    PAGE_HEADER,
    TABLE,
    TABLE_WRAP,
    btn,
)

ar = APIRouter()

_PERIODS = ["daily", "weekly", "monthly", "quarterly", "yearly"]


def _detail_redirect(sub_id: int, msg: str = "", kind: str = "warning",
                     tab: str = "periods"):
    url = f"/subscriptions/{sub_id}/detail?tab={tab}"
    if msg:
        url += f"&msg={quote_plus(msg)}&msg_kind={kind}"
    return RedirectResponse(url, status_code=303)


# ── New subscription ─────────────────────────────────────────────────────────

@ar("/manage/new")
def get(req, session):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_CREATE)): return r
    if not writable_team(ctx):
        return page_title("New Subscription"), nav_bar(ctx, "manage"), Main(
            Div(H2("Add Subscription"), A("← Manage", href="/manage", cls=LINK), cls=PAGE_HEADER),
            alert("Switch to a specific team (not “All teams”) before adding a "
                  "subscription.", "warning"),
        )
    db = get_db()
    return page_title("New Subscription"), nav_bar(ctx, "manage"), Main(
        Div(H2("Add Subscription"), A("← Manage", href="/manage", cls=LINK), cls=PAGE_HEADER),
        subscription_form("/manage/new", btn_label="Create Subscription",
                          categories=get_categories(db, ctx), include_period=True),
    )


@ar("/manage/new")
async def post(req, session, name: str, amount: float, start_date: str,
               end_date: str = "", frequency: str = "monthly",
               interval: int = 1, base_unit: str = "", notes: str = "",
               category: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_CREATE)): return r
    if not writable_team(ctx):
        return RedirectResponse("/teams?msg=Switch+to+a+specific+team+first&msg_kind=warning",
                                status_code=303)
    db = get_db()
    now = timeutil.now_iso()
    frequency, interval_val, base_unit_val = normalise_cadence(frequency, interval, base_unit)
    category_val = category.strip() or None

    # Validate the first period before creating anything, so a bad date or amount
    # re-renders the form (with the entered values) instead of leaving a
    # period-less subscription behind.
    err = validate_periods([{"start_date": start_date, "end_date": end_date or None,
                             "amount": amount}])
    if err:
        return page_title("New Subscription"), nav_bar(ctx, "manage"), Main(
            Div(H2("Add Subscription"), A("← Manage", href="/manage", cls=LINK), cls=PAGE_HEADER),
            alert(err, "error"),
            subscription_form(
                "/manage/new", btn_label="Create Subscription",
                categories=get_categories(db, ctx), include_period=True,
                sub={"name": name, "category": category_val, "frequency": frequency,
                     "interval": interval_val, "base_unit": base_unit_val, "notes": notes},
                period={"amount": amount, "start_date": start_date, "end_date": end_date or ""}),
        )

    sub_id = db["subscriptions"].insert({
        "team_id": ctx.active_team_id, "created_by": ctx.user["id"],
        "name": name, "currency": "EUR", "category": category_val, "notes": notes,
        "frequency": frequency, "interval": interval_val, "base_unit": base_unit_val,
        "created_at": now, "updated_at": now,
    }).last_pk

    add_period(db, sub_id, amount, start_date, end_date or None, ctx.user["id"])  # fresh sub: never auto-closes

    audit(ctx, "CREATE", "subscription", sub_id, name,
          f"Created '{name}' €{amount}/{frequency}",
          new_values={"name": name, "amount": amount, "category": category_val,
                      "frequency": frequency, "interval": interval_val,
                      "base_unit": base_unit_val, "start_date": start_date,
                      "end_date": end_date or None})
    return RedirectResponse("/manage", status_code=303)


# ── Edit subscription (identity + cadence only) ──────────────────────────────

@ar("/subscriptions/{sub_id}/edit")
def get(req, session, sub_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_EDIT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)
    return page_title(f"Edit {sub['name']}"), nav_bar(ctx, "manage"), Main(
        Div(H2(f"Edit: {sub['name']}"),
            A("← Back", href=f"/subscriptions/{sub_id}/detail", cls=LINK),
            cls=PAGE_HEADER),
        alert("This edits the subscription's name, billing frequency and details. "
              "Prices and active dates are managed as periods on the detail page.", "info"),
        subscription_form(f"/subscriptions/{sub_id}/edit", sub=sub,
                          btn_label="Update Subscription",
                          categories=get_categories(db, ctx)),
    )


@ar("/subscriptions/{sub_id}/edit")
async def post(req, session, sub_id: int, name: str, frequency: str = "monthly",
               interval: int = 1, base_unit: str = "", notes: str = "",
               category: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_EDIT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)

    frequency, interval_val, base_unit_val = normalise_cadence(frequency, interval, base_unit)
    category_val = category.strip() or None
    fields = ["name", "category", "frequency", "interval", "base_unit", "notes"]
    old = {k: sub[k] for k in fields}
    new_vals = {"name": name, "category": category_val, "frequency": frequency,
                "interval": interval_val, "base_unit": base_unit_val, "notes": notes}
    changed = {k: v for k, v in new_vals.items() if str(v) != str(old.get(k, ""))}

    db["subscriptions"].update(sub_id, {**new_vals, "updated_at": timeutil.now_iso()})
    audit(ctx, "UPDATE", "subscription", sub_id, name, f"Updated '{name}'",
          old_values={k: old[k] for k in changed}, new_values=changed)
    return RedirectResponse(f"/subscriptions/{sub_id}/detail", status_code=303)


# ── Add a period ─────────────────────────────────────────────────────────────

@ar("/subscriptions/{sub_id}/periods/add")
async def post(req, session, sub_id: int, amount: float, start_date: str,
               end_date: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_EDIT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)

    err, note = add_period(db, sub_id, amount, start_date, end_date or None, ctx.user["id"])
    if err:
        return _detail_redirect(sub_id, err, "error")

    db["subscriptions"].update(sub_id, {"updated_at": timeutil.now_iso()})
    desc = (f"Added period for '{sub['name']}': {fmt_eur(amount)} from {start_date}"
            f"{(' to ' + end_date) if end_date else ' (open-ended)'}")
    if note:
        desc += f" — {note}"
    audit(ctx, "ADD_PERIOD", "subscription", sub_id, sub["name"], desc,
          new_values={"amount": amount, "start_date": start_date, "end_date": end_date or None})
    return _detail_redirect(sub_id, ("Period added. " + note).strip(), "success")


# ── Edit a period ────────────────────────────────────────────────────────────

@ar("/subscriptions/{sub_id}/periods/{period_id}/edit")
def get(req, session, sub_id: int, period_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_EDIT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)
    period = next((p for p in get_periods(db, sub_id) if p["id"] == period_id), None)
    if not period:
        return _detail_redirect(sub_id)

    return page_title(f"Edit Period – {sub['name']}"), nav_bar(ctx, "manage"), Main(
        Div(H2(f"Edit Period: {sub['name']}"),
            A("← Back", href=f"/subscriptions/{sub_id}/detail?tab=periods", cls=LINK),
            cls=PAGE_HEADER),
        Form(
            Label("Amount (€) *",
                  Input(name="amount", type="number", step="0.01", min="0",
                        value=period["amount"], required=True, cls=INPUT),
                  cls="grid gap-1.5 text-sm font-medium"),
            Label("Start Date *",
                  Input(name="start_date", type="date", value=period["start_date"],
                        required=True, cls=INPUT),
                  cls="grid gap-1.5 text-sm font-medium"),
            Label("End Date",
                  Input(name="end_date", type="date", value=period["end_date"] or "", cls=INPUT),
                  cls="grid gap-1.5 text-sm font-medium"),
            Button("Save Period", type="submit", cls=btn("outline")),
            method="post", action=f"/subscriptions/{sub_id}/periods/{period_id}/edit",
            cls="grid gap-4 max-w-md",
        ),
    )


@ar("/subscriptions/{sub_id}/periods/{period_id}/edit")
async def post(req, session, sub_id: int, period_id: int, amount: float,
               start_date: str, end_date: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_EDIT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)

    err = update_period(db, sub_id, period_id, amount, start_date, end_date or None)
    if err:
        return _detail_redirect(sub_id, err, "error")

    db["subscriptions"].update(sub_id, {"updated_at": timeutil.now_iso()})
    audit(ctx, "EDIT_PERIOD", "subscription", sub_id, sub["name"],
          f"Edited period for '{sub['name']}': {fmt_eur(amount)} from {start_date}"
          f"{(' to ' + end_date) if end_date else ' (open-ended)'}",
          new_values={"amount": amount, "start_date": start_date, "end_date": end_date or None})
    return _detail_redirect(sub_id, "Period updated.", "success")


# ── Delete a period ──────────────────────────────────────────────────────────

@ar("/subscriptions/{sub_id}/periods/{period_id}/delete")
async def post(req, session, sub_id: int, period_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_EDIT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)

    period = next((p for p in get_periods(db, sub_id) if p["id"] == period_id), None)
    if not period:
        return _detail_redirect(sub_id)
    delete_period(db, period_id, sub_id)

    db["subscriptions"].update(sub_id, {"updated_at": timeutil.now_iso()})
    audit(ctx, "DELETE_PERIOD", "subscription", sub_id, sub["name"],
          f"Deleted period for '{sub['name']}': {fmt_eur(period['amount'])} "
          f"from {period['start_date']}",
          old_values={"amount": period["amount"], "start_date": period["start_date"],
                      "end_date": period["end_date"]})
    return _detail_redirect(sub_id, "Period deleted.", "success")


# ── Subscription detail ──────────────────────────────────────────────────────

# The detail page is split into linked tabs (?tab=…) instead of one long stack of
# cards: the summary header + figures always show, and each tab holds one concern.
_TAB_KEYS = ["overview", "spend", "periods", "history"]


def _kv(label, value):
    return Div(Div(label, cls="text-xs text-muted-foreground mb-0.5"), Div(value))


def _figure(label, value, caption=None):
    return Div(
        Div(label, cls=COST_LABEL),
        Div(value, cls=COST_AMOUNT),
        Div(caption, cls="text-xs text-muted-foreground mt-1 truncate") if caption else "",
        cls=COST_CARD,
    )


def _relative_day(d: date, today: date) -> str:
    days = (d - today).days
    if days == 0: return "today"
    if days == 1: return "tomorrow"
    return f"in {days} days" if days > 0 else f"{-days} days ago"


def _detail_header(sub, price, freq_lbl, active, next_pay, today, actions):
    """Name + status + current price + next payment + actions, in one card."""
    subtitle = freq_lbl
    if next_pay:
        subtitle += f" · next {next_pay['date'].isoformat()} ({_relative_day(next_pay['date'], today)})"
    return Div(
        Div(
            H2(sub["name"], cls="truncate"),
            Div(status_badge(active),
                badge(category_label(sub.get("category")), "info"),
                cls="flex flex-wrap items-center gap-2 mt-2"),
            cls="min-w-0 flex-1",
        ),
        Div(
            Div(fmt_eur(price) if price is not None else "—",
                cls="text-3xl font-bold tracking-tight"),
            Div(subtitle, cls=MUTED_SM),
            cls="sm:text-right",
        ),
        Div(*actions, cls="flex gap-2 flex-wrap") if actions else "",
        cls="flex flex-wrap items-start justify-between gap-4 rounded-xl border "
            "bg-card p-5 mb-4",
    )


def _overview_tab(sub, periods, price, freq_lbl, upcoming, today, can_edit):
    started = min((p["start_date"] for p in periods), default=None)
    ends = next((p["end_date"] for p in sorted(periods, key=lambda p: p["start_date"],
                                               reverse=True)), None)

    details = section_card(
        Div(
            _kv("Current price", Strong(fmt_eur(price)) if price is not None else "—"),
            _kv("Billing frequency", freq_lbl),
            _kv("Category", badge(category_label(sub.get("category")), "info")),
            _kv("Currency", sub["currency"] or "EUR"),
            _kv("Tracking since", started or "—"),
            _kv("Ends", ends or "open-ended"),
            cls="grid grid-cols-2 sm:grid-cols-3 gap-4",
        ),
        Div(Div("Notes", cls="text-xs text-muted-foreground mb-0.5"),
            Div(sub["notes"] or "—", cls="whitespace-pre-line"),
            cls="mt-4 pt-4 border-t"),
        heading="Details",
    )

    costs = section_card(
        Div(Table(
            Thead(Tr(*[Th(p.capitalize()) for p in _PERIODS])),
            Tbody(Tr(*[Td(fmt_eur(get_period_cost(
                              price or 0.0, sub["frequency"], sub["interval"] or 1,
                              sub.get("base_unit"), p)), cls="nowrap")
                       for p in _PERIODS])),
            cls=TABLE,
        ), cls=TABLE_WRAP),
        P("The same price expressed per period — useful for comparing subscriptions "
          "that bill on different cadences.", cls=MUTED_SM + " mt-2"),
        heading="What it costs per period",
    ) if price is not None else ""

    if upcoming:
        rows = [
            Div(
                Span(pay["date"].isoformat(), cls="tabular-nums"),
                Span(Span(_relative_day(pay["date"], today),
                          cls="text-muted-foreground text-sm mr-3"),
                     Strong(fmt_eur(pay["amount"]), cls="tabular-nums")),
                cls="flex justify-between items-center py-2 border-b last:border-0",
            )
            for pay in upcoming
        ]
        total = round(sum(p["amount"] for p in upcoming), 2)
        payments = section_card(
            *rows,
            P(f"Next {len(upcoming)} payments add up to {fmt_eur(total)}.",
              cls=MUTED_SM + " mt-3"),
            heading="Next expected payments",
        )
    else:
        hint = (" Add a period covering today to start tracking payments again."
                if can_edit else "")
        payments = section_card(
            P("No upcoming payments — this subscription is not currently active." + hint,
              cls=MUTED_SM),
            heading="Next expected payments",
        )

    return [details, Div(costs, payments, cls=CHARTS_GRID) if costs else payments]


def _spend_tab(sub, periods, today):
    if not periods:
        return [section_card(P("No periods recorded yet, so there is nothing to chart.",
                               cls=MUTED_SM), heading="Spend over time")]
    year = today.year
    monthly = monthly_costs_for_year(sub, periods, year)
    year_total = year_cost(sub, periods, year)
    first_start = date.fromisoformat(min(p["start_date"] for p in periods))
    lifetime = range_cost(sub, periods, first_start, today)
    months_tracked = max(1, (today - first_start).days / 30.4375)

    return [
        Div(
            _figure(f"This year ({year})", fmt_eur(year_total)),
            _figure("All-time", fmt_eur(lifetime), f"since {first_start.isoformat()}"),
            _figure("Average / month", fmt_eur(round(lifetime / months_tracked, 2)),
                    "over the tracked period"),
            cls="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5",
        ),
        section_card(
            bar_chart(MONTH_LABELS, monthly,
                      tip_labels=[f"{calendar.month_name[m + 1]} {year}" for m in range(12)]),
            P("Cost is spread across the days each period was active — hover a bar for "
              "the exact amount, click to keep it open.", cls=MUTED_SM),
            heading=f"Monthly spend in {year}",
        ),
    ]


def _periods_tab(sub_id, periods, today_iso, can_edit):
    def period_status(p):
        if p["start_date"] <= today_iso and (p["end_date"] is None or p["end_date"] >= today_iso):
            return badge("Active", "active")
        if p["start_date"] > today_iso:
            return badge("Upcoming", "info")
        return badge("Ended", "inactive")

    rows = [
        Tr(
            Td(fmt_eur(p["amount"]), cls="nowrap tabular-nums"),
            Td(p["start_date"], cls="nowrap tabular-nums"),
            Td(p["end_date"] or "open-ended", cls="nowrap tabular-nums"),
            Td(period_status(p), cls="nowrap"),
            Td(
                Div(
                    A("✏️", href=f"/subscriptions/{sub_id}/periods/{p['id']}/edit",
                      role="button", cls=btn("outline", "sm"), title="Edit period",
                      **{"aria-label": "Edit period"}),
                    Button("🗑️", cls=btn("outline", "sm"), title="Delete period",
                           **{"aria-label": "Delete period"},
                           hx_post=f"/subscriptions/{sub_id}/periods/{p['id']}/delete",
                           hx_confirm=f"Delete period {fmt_eur(p['amount'])} from {p['start_date']}?",
                           hx_target="body", hx_push_url="true"),
                    cls="flex gap-1",
                ) if can_edit else "", cls="nowrap"),
        )
        for p in periods
    ]

    table = (Div(Table(
        Thead(Tr(Th("Amount"), Th("Start"), Th("End"), Th("Status"),
                 *([Th("")] if can_edit else []))),
        Tbody(*rows), cls=TABLE,
    ), cls=TABLE_WRAP) if rows else P("No periods yet — add the first one below.",
                                      cls=MUTED_SM))

    out = [section_card(
        P("A period is one stretch of time at one price. Add a new period when the "
          "price changes or the subscription pauses and resumes; the old one is closed "
          "automatically.", cls=MUTED_SM + " mb-3"),
        table,
        heading="Periods",
    )]

    if can_edit:
        out.append(section_card(
            Form(
                Div(
                    Label("Amount (€) *",
                          Input(name="amount", type="number", step="0.01", min="0",
                                required=True, cls=INPUT),
                          cls="grid gap-1.5 text-sm font-medium"),
                    Label("Start Date *",
                          Input(name="start_date", type="date", value=today_iso,
                                required=True, cls=INPUT),
                          cls="grid gap-1.5 text-sm font-medium"),
                    Label("End Date",
                          Input(name="end_date", type="date", cls=INPUT),
                          cls="grid gap-1.5 text-sm font-medium"),
                    Div(Button("Add Period", type="submit", cls=btn()),
                        cls="flex items-end"),
                    cls="grid gap-3 sm:grid-cols-4 items-start",
                ),
                method="post", action=f"/subscriptions/{sub_id}/periods/add",
            ),
            heading="Add a period",
        ))
    return out


def _history_tab(audit_entries):
    if not audit_entries:
        return [section_card(P("No audit entries yet.", cls=MUTED_SM), heading="History")]
    rows = [
        Tr(Td(a["timestamp"][:16], cls="nowrap tabular-nums"), Td(a["action"], cls="nowrap"),
           Td(a["description"]))
        for a in audit_entries
    ]
    return [section_card(
        Div(Table(Thead(Tr(Th("Time"), Th("Action"), Th("Description"))),
                  Tbody(*rows), cls=TABLE), cls=TABLE_WRAP),
        heading=f"History ({len(audit_entries)} entries)",
    )]


@ar("/subscriptions/{sub_id}/detail")
def get(req, session, sub_id: int, tab: str = "overview", msg: str = "",
        msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_VIEW)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)

    today = timeutil.today()
    today_iso = today.isoformat()
    periods = get_periods(db, sub_id)
    active = is_active_on(periods, today_iso)
    price = current_price(periods)
    freq_lbl = frequency_label(sub["frequency"], sub["interval"] or 1, sub.get("base_unit"))
    upcoming = upcoming_payments_for_periods(sub, periods, count=6, reference=today)

    can_edit = ctx.can(Perm.SUB_EDIT)
    can_delete = ctx.can(Perm.SUB_DELETE)
    can_audit = ctx.can(Perm.AUDIT_VIEW)

    actions = []
    if can_edit:
        actions.append(
            A("✏️ Edit", href=f"/subscriptions/{sub_id}/edit", role="button", cls=btn("outline")))
    if can_delete:
        actions.append(Button("🗑️ Delete",
                       hx_post=f"/subscriptions/{sub_id}/delete",
                       hx_confirm=f"Delete '{sub['name']}'? (soft-delete)",
                       hx_target="body", hx_push_url="true", cls=btn("destructive")))

    tabs = [("overview", "Overview"), ("spend", "Spend"),
            ("periods", "Periods", len(periods))]
    audit_entries = get_audit_for_entity(db, sub_id, "subscription") if can_audit else []
    if can_audit:
        tabs.append(("history", "History", len(audit_entries)))
    # An unknown (or no-longer-permitted) tab falls back to the overview.
    if tab not in {t[0] for t in tabs}:
        tab = "overview"

    if tab == "spend":
        panels = _spend_tab(sub, periods, today)
    elif tab == "periods":
        panels = _periods_tab(sub_id, periods, today_iso, can_edit)
    elif tab == "history":
        panels = _history_tab(audit_entries)
    else:
        panels = _overview_tab(sub, periods, price, freq_lbl, upcoming, today, can_edit)

    return page_title(sub["name"]), nav_bar(ctx, "manage"), Main(
        A("← All subscriptions", href="/manage", cls=LINK + " inline-block mb-3"),
        alert(msg, msg_kind) if msg else "",
        _detail_header(sub, price, freq_lbl, active, upcoming[0] if upcoming else None,
                       today, actions),
        tab_nav(tabs, tab, lambda k: f"/subscriptions/{sub_id}/detail?tab={k}"),
        *panels,
    )


# ── Soft-delete a subscription ───────────────────────────────────────────────

@ar("/subscriptions/{sub_id}/delete")
async def post(req, session, sub_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_DELETE)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id)
    if not sub:
        return RedirectResponse("/manage", status_code=303)

    now = timeutil.now_iso()
    db["subscriptions"].update(sub_id, {
        "deleted_at": now, "deleted_by": ctx.user["id"], "updated_at": now,
    })
    audit(ctx, "DELETE", "subscription", sub_id, sub["name"],
          f"Soft-deleted '{sub['name']}'",
          old_values={"deleted_at": None},
          new_values={"deleted_at": now, "deleted_by": ctx.user["id"]})
    return RedirectResponse("/manage", status_code=303)
