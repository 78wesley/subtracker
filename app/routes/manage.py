"""
manage.py — Subscription list with search / status / category filters.

Status and the displayed price are derived from each subscription's periods
(see app.db.subscriptions): a sub is active when a period covers today.
"""

from urllib.parse import urlencode

from fasthtml.common import *

from app import timeutil
from app.authz import require
from app.components import (
    action_menu,
    badge,
    category_label,
    fmt_eur,
    nav_bar,
    page_title,
    pagination_bar,
    select_menu,
    status_badge,
)
from app.cost_utils import frequency_label
from app.db import (
    current_price,
    get_all_subscriptions,
    get_categories,
    get_db,
    get_periods_map,
    is_active_on,
    upcoming_price_change,
)
from app.permissions import Perm
from app.styles import CONTROL, PAGE_HEADER, TABLE, btn

_FF = "grid gap-1.5 text-sm font-medium"  # filter field (label + control)
_PER_PAGE = 20  # subscriptions per page in the manage list

# lucide arrow-up-right — signals the name links through to the detail page.
_OPEN_ICON = NotStr(
    '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" class="opacity-50 shrink-0"><path d="M7 7h10v10"/>'
    '<path d="M7 17 17 7"/></svg>'
)

# lucide trending-up / trending-down — marks a queued future price change.
_TREND_UP = ('<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" '
             'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>'
             '<polyline points="16 7 22 7 22 13"/></svg>')
_TREND_DOWN = ('<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" '
               'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
               'stroke-linejoin="round"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/>'
               '<polyline points="16 17 22 17 22 11"/></svg>')


def _price_change_icon(change) -> object:
    """Small trend icon (with tooltip) for an upcoming price change, else ''."""
    if not change:
        return ""
    up = change["amount"] > change["current"]
    return Span(
        NotStr(_TREND_UP if up else _TREND_DOWN),
        cls="shrink-0 " + ("text-warning" if up else "text-success"),
        title=f"Price {'rises' if up else 'drops'} to {fmt_eur(change['amount'])} "
              f"on {change['start_date']}",
    )


ar = APIRouter()


# ── Manage list ──────────────────────────────────────────────────────────────

@ar("/manage")
def get(req, session, q: str = "", status: str = "all", category: str = "", page: int = 1):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_VIEW)): return r
    db = get_db()

    can_create = ctx.can(Perm.SUB_CREATE)
    can_edit = ctx.can(Perm.SUB_EDIT)
    can_delete = ctx.can(Perm.SUB_DELETE)
    can_view_detail = ctx.can(Perm.SUB_VIEW)
    show_actions = can_edit or can_delete

    today = timeutil.today_iso()
    all_categories = get_categories(db, ctx)
    subs = get_all_subscriptions(db, ctx,
                                 filter_active=status if status != "all" else None,
                                 search=q or None,
                                 category=category or None)

    total_pages = max(1, (len(subs) + _PER_PAGE - 1) // _PER_PAGE)
    page = max(1, min(page, total_pages))
    page_subs = subs[(page - 1) * _PER_PAGE: page * _PER_PAGE]

    periods_map = get_periods_map(db, [s["id"] for s in page_subs])
    rows = []
    for s in page_subs:
        periods = periods_map.get(s["id"], [])
        price = current_price(periods, today)
        active = is_active_on(periods, today)
        price_change = upcoming_price_change(periods, today)
        notes = s["notes"] or ""
        name_cell = (
            A(s["name"], _OPEN_ICON, href=f"/subscriptions/{s['id']}/detail",
              cls="inline-flex items-center gap-1 font-medium hover:underline")
            if can_view_detail else Span(s["name"], cls="font-medium")
        )
        rows.append(Tr(
            Td(name_cell),
            Td(badge(category_label(s.get("category")), "info"), cls="nowrap"),
            Td(Span(fmt_eur(price) if price is not None else "—",
                    _price_change_icon(price_change),
                    cls="inline-flex items-center gap-1.5"), cls="nowrap"),
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

    actions = [Button("Filter", type="submit", cls=btn("outline"))]
    if can_create:
        actions.append(A("＋ Add", href="/manage/new", role="button", cls=btn("outline")))

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

    base_url = "/manage?" + urlencode({"q": q, "status": status, "category": category})
    pager = pagination_bar(page, total_pages, base_url) if total_pages > 1 else ""

    return page_title("Manage"), nav_bar(ctx, "manage"), Main(
        Div(H2("Manage Subscriptions"),
            A("Import / Export", href="/import", role="button", cls=btn("outline")),
            cls=PAGE_HEADER),
        filter_bar,
        table,
        pager,
    )
