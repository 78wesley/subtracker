"""
subscriptions.py — Create / edit / period management / detail / soft-delete.

A subscription carries identity + cadence; its dated active windows and prices live
in subscription_periods (multiple, non-overlapping). "Active" and "current price"
are derived from those periods. All reads go through the team-scoped
get_subscription(db, ctx, ...); all writes are gated by require(ctx, ...) and audited.
"""

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
    collapsible_card,
    fmt_eur,
    nav_bar,
    page_title,
    section_card,
    status_badge,
    subscription_form,
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
from app.styles import INPUT, LINK, MUTED_SM, PAGE_HEADER, TABLE, TABLE_WRAP, btn

ar = APIRouter()

_PERIODS = ["daily", "weekly", "monthly", "quarterly", "yearly"]


def _detail_redirect(sub_id: int, msg: str = "", kind: str = "warning"):
    url = f"/subscriptions/{sub_id}/detail"
    if msg:
        url += f"?msg={quote_plus(msg)}&msg_kind={kind}"
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
            A("← Back", href=f"/subscriptions/{sub_id}/detail", cls=LINK),
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

@ar("/subscriptions/{sub_id}/detail")
def get(req, session, sub_id: int, msg: str = "", msg_kind: str = "warning"):
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
    audit_entries = get_audit_for_entity(db, sub_id, "subscription")
    freq_lbl = frequency_label(sub["frequency"], sub["interval"] or 1, sub.get("base_unit"))

    can_edit = ctx.can(Perm.SUB_EDIT)
    can_delete = ctx.can(Perm.SUB_DELETE)
    actions = []
    if can_edit:
        actions.append(
            A("✏️ Edit", href=f"/subscriptions/{sub_id}/edit", role="button", cls=btn("outline")))
    if can_delete:
        actions.append(Button("🗑️ Delete",
                       hx_post=f"/subscriptions/{sub_id}/delete",
                       hx_confirm=f"Delete '{sub['name']}'? (soft-delete)",
                       hx_target="body", hx_push_url="true", cls=btn("destructive")))

    def kv(label, value):
        return Div(Div(label, cls="text-xs text-muted-foreground mb-0.5"), Div(value))

    info = section_card(
        H3(sub["name"]),
        Div(
            kv("Current Price", Strong(fmt_eur(price)) if price is not None else "—"),
            kv("Frequency", freq_lbl),
            kv("Status", status_badge(active)),
            kv("Category", badge(category_label(sub.get("category")), "info")),
            kv("Currency", sub["currency"] or "EUR"),
            cls="grid grid-cols-2 sm:grid-cols-3 gap-4 my-4",
        ),
        Div(Div("Notes", cls="text-xs text-muted-foreground mb-0.5"), Div(sub["notes"] or "—")),
        Div(*actions, cls="flex gap-2 flex-wrap mt-4") if actions else "",
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
        heading="Cost Breakdown (current price)",
    ) if price is not None else ""

    # Spend-over-time charts for the current year + lifetime total.
    spend_section = ""
    if periods:
        year = today.year
        monthly = monthly_costs_for_year(sub, periods, year)
        year_total = year_cost(sub, periods, year)
        first_start = date.fromisoformat(min(p["start_date"] for p in periods))
        lifetime = range_cost(sub, periods, first_start, today)

        def figure(label, value):
            return Div(Div(label, cls="text-xs text-muted-foreground"),
                       Div(fmt_eur(value), cls="text-2xl font-semibold tracking-tight"))

        spend_section = section_card(
            Div(figure(f"This year ({year})", year_total),
                figure("All-time", lifetime),
                cls="flex gap-10 mb-4"),
            Div(P("Monthly spend", cls="text-sm font-medium text-muted-foreground mb-2"),
                bar_chart(MONTH_LABELS, monthly)),
            heading=f"Spend over time ({year})",
        )

    def period_status(p):
        if p["start_date"] <= today_iso and (p["end_date"] is None or p["end_date"] >= today_iso):
            return badge("Active", "active")
        if p["start_date"] > today_iso:
            return badge("Upcoming", "info")
        return badge("Ended", "inactive")

    period_rows = [
        Tr(
            Td(fmt_eur(p["amount"]), cls="nowrap"),
            Td(p["start_date"], cls="nowrap"),
            Td(p["end_date"] or "open-ended", cls="nowrap"),
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

    add_period_form = (
        section_card(
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
                    Div(Button("Add Period", type="submit", cls=btn("outline")),
                        cls="flex items-end"),
                    cls="grid gap-3 sm:grid-cols-4 items-start",
                ),
                method="post", action=f"/subscriptions/{sub_id}/periods/add",
            ),
            heading="Add Period",
        ) if can_edit else ""
    )

    periods_section = section_card(
        heading="Periods",
        *([Div(Table(
            Thead(Tr(Th("Amount"), Th("Start"), Th("End"), Th("Status"),
                     *([Th("")] if can_edit else []))),
            Tbody(*period_rows), cls=TABLE,
        ), cls=TABLE_WRAP)] if period_rows else [P("No periods yet. Add one below.", cls=MUTED_SM)]),
    )

    upcoming = []
    for pay in upcoming_payments_for_periods(sub, periods, count=6, reference=today):
        days_from_now = (pay["date"] - today).days
        label = "today" if days_from_now == 0 else (
            f"in {days_from_now} day{'s' if days_from_now != 1 else ''}"
            if days_from_now > 0 else f"{-days_from_now}d ago"
        )
        upcoming.append(Div(
            Span(pay["date"].isoformat()),
            Span(Span(label, cls="text-muted-foreground text-sm mr-2"),
                 Strong(fmt_eur(pay["amount"]))),
            cls="flex justify-between items-center py-2 border-b last:border-0",
        ))

    next_payments = section_card(
        heading="Next Expected Payments",
        *(upcoming if upcoming else [P("No upcoming payments — subscription is not "
                                       "currently active.")]),
    )

    audit_rows = [
        Tr(Td(a["timestamp"][:16], cls="nowrap"), Td(a["action"], cls="nowrap"),
           Td(a["description"]))
        for a in audit_entries
    ]
    # Audit history is hidden from roles without audit access (e.g. viewers).
    audit_section = collapsible_card(
        f"Audit Log ({len(audit_entries)} entries)",
        Div(Table(
            Thead(Tr(Th("Time"), Th("Action"), Th("Description"))),
            Tbody(*audit_rows), cls=TABLE,
        ), cls=TABLE_WRAP) if audit_rows else P("No audit entries.", cls=MUTED_SM),
    ) if ctx.can(Perm.AUDIT_VIEW) else ""

    return page_title(sub["name"]), nav_bar(ctx, "manage"), Main(
        Div(H2(sub["name"]), A("← Manage", href="/manage", cls=LINK), cls=PAGE_HEADER),
        alert(msg, msg_kind) if msg else "",
        info, costs, spend_section, periods_section, add_period_form, next_payments, audit_section,
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
