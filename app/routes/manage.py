"""
manage.py — Subscription list with search / status / category filters.

Status and the displayed price are derived from each subscription's periods
(see app.db.subscriptions): a sub is active when a period covers today.
"""

from fasthtml.common import *

from app import timeutil
from app.db import (
    get_db, get_all_subscriptions, get_categories, get_periods_map,
    current_price, is_active_on,
)
from app.authz import require
from app.cost_utils import frequency_label
from app.components import (
    page_title, nav_bar, badge, status_badge, action_menu,
    select_menu, fmt_eur, category_label,
)
from app.styles import PAGE_HEADER, TABLE, CONTROL, btn

_FF = "grid gap-1.5 text-sm font-medium"  # filter field (label + control)

# lucide arrow-up-right — signals the name links through to the detail page.
_OPEN_ICON = NotStr(
    '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" class="opacity-50 shrink-0"><path d="M7 7h10v10"/>'
    '<path d="M7 17 17 7"/></svg>'
)

ar = APIRouter()


# ── Manage list ──────────────────────────────────────────────────────────────

@ar("/manage")
def get(req, session, q: str = "", status: str = "all", category: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "subscriptions.view")): return r
    db = get_db()

    can_create = ctx.can("subscriptions.create")
    can_edit = ctx.can("subscriptions.edit")
    can_delete = ctx.can("subscriptions.delete")
    can_view_detail = ctx.can("subscriptions.view")
    show_actions = can_edit or can_delete

    today = timeutil.today_iso()
    all_categories = get_categories(db, ctx)
    subs = get_all_subscriptions(db, ctx,
                                 filter_active=status if status != "all" else None,
                                 search=q or None,
                                 category=category or None)
    periods_map = get_periods_map(db, [s["id"] for s in subs])
    rows = []
    for s in subs:
        periods = periods_map.get(s["id"], [])
        price = current_price(periods, today)
        active = is_active_on(periods, today)
        notes = s["notes"] or ""
        name_cell = (
            A(s["name"], _OPEN_ICON, href=f"/subscriptions/{s['id']}/detail",
              cls="inline-flex items-center gap-1 font-medium hover:underline")
            if can_view_detail else Span(s["name"], cls="font-medium")
        )
        rows.append(Tr(
            Td(name_cell),
            Td(badge(category_label(s.get("category")), "info"), cls="nowrap"),
            Td(fmt_eur(price) if price is not None else "—", cls="nowrap"),
            Td(frequency_label(s["frequency"], s["interval"] or 1, s.get("base_unit")),
               cls="nowrap"),
            Td(status_badge(active), cls="nowrap"),
            Td(Div(notes, cls="line-clamp-2 max-w-[18rem]", title=notes) if notes else "—"),
            *([Td(action_menu(s["id"], s["name"], can_edit=can_edit, can_delete=can_delete),
                  cls="nowrap")] if show_actions else []),
        ))

    empty_state = (
        P("No subscriptions found. ", A("Add one →", href="/manage/new", cls="underline"))
        if can_create else P("No subscriptions found.")
    )
    table = (
        Div(Table(
            Thead(Tr(Th("Name"), Th("Category"), Th("Price"), Th("Frequency"),
                     Th("Status"), Th("Notes"),
                     *([Th("Actions")] if show_actions else []))),
            Tbody(*rows), cls=TABLE,
        ), cls="rounded-xl border bg-card overflow-x-auto")
        if rows else empty_state
    )

    actions = [Button("Filter", type="submit", cls=btn())]
    if can_create:
        actions.append(A("＋ Add", href="/manage/new", role="button", cls=btn()))

    filter_bar = Form(
        Div(
            Label("Search", Input(name="q", value=q, placeholder="Search name…",
                                  cls=CONTROL + " w-[200px]"), cls=_FF),
            Label("Status", select_menu("status",
                [("all", "All"), ("active", "Active"), ("inactive", "Inactive")],
                value=status, width="w-[130px]"), cls=_FF),
            Label("Category", select_menu("category",
                [("", "All")] + [(c, c) for c in all_categories],
                value=category, width="w-[170px]"), cls=_FF),
            *actions,
            cls="flex flex-wrap items-end gap-3 mb-4",
        ),
        method="get", action="/manage",
    )

    return page_title("Manage"), nav_bar(ctx, "manage"), Main(
        Div(H2("Manage Subscriptions"), cls=PAGE_HEADER),
        filter_bar,
        table,
    )
