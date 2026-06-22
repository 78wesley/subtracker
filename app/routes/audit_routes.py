"""
audit_routes.py — Audit log viewer (paginated, filterable by action).
"""

from fasthtml.common import *

from app.authz import require
from app.components import (
    badge,
    json_pretty,
    nav_bar,
    page_title,
    pagination_bar,
    select_menu,
)
from app.db import get_audit_log, get_db
from app.permissions import Perm
from app.styles import MUTED, PAGE_HEADER, TABLE, btn

ar = APIRouter()


@ar("/audit")
def get(req, session, action_filter: str = "", page: int = 1):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.AUDIT_VIEW)): return r
    db = get_db()

    entries, total = get_audit_log(db, ctx,
                                   action_filter=action_filter or None, page=page)
    total_pages = max(1, (total + 24) // 25)
    actions = ["LOGIN", "LOGOUT", "CREATE", "UPDATE", "DELETE", "PRICE_CHANGE",
               "RESTORE", "PERMANENT_DELETE", "ROLE_CHANGE", "TEAM_CREATE", "MEMBER_ADD"]
    scope_note = ("all teams" if (ctx.view_all and ctx.is_super) else
                  (f"team: {ctx.active_team_name}" if ctx.can(Perm.AUDIT_VIEW) and ctx.active_team_name
                   else "your actions"))

    filter_bar = Form(
        Div(
            Label("Action", select_menu("action_filter",
                [("", "All Actions")] + [(a, a) for a in actions],
                value=action_filter, width="w-[180px]"),
                cls="grid gap-1.5 text-sm font-medium"),
            Button("Filter", type="submit", cls=btn("outline")),
            cls="flex flex-wrap items-end gap-3 mb-4",
        ),
        method="get", action="/audit",
    )

    _pre = "text-xs whitespace-pre-wrap break-all max-w-[18rem] text-muted-foreground"
    rows = [
        Tr(
            Td(e["timestamp"][:16], cls="nowrap"),
            Td(e.get("actor_name") or "—", cls="nowrap"),
            Td(badge(e["action"], "secondary"), cls="nowrap"),
            Td(Div(e["entity_type"]),
               Small(e.get("entity_name") or "", cls=MUTED)),
            Td(e["description"]),
            Td(Pre(json_pretty(e["old_values"]), cls=_pre) if e["old_values"] else "—"),
            Td(Pre(json_pretty(e["new_values"]), cls=_pre) if e["new_values"] else "—"),
        )
        for e in entries
    ]

    return page_title("Audit Log"), nav_bar(ctx, "audit"), Main(
        Div(H2("Audit Log ", Small(f"· {scope_note}", cls="text-muted-foreground font-normal")),
            cls=PAGE_HEADER),
        filter_bar,
        Div(Table(
            Thead(Tr(Th("Time"), Th("Actor"), Th("Action"), Th("Entity"),
                     Th("Description"), Th("Old"), Th("New"))),
            Tbody(*rows), cls=TABLE,
        ), cls="rounded-xl border bg-card overflow-x-auto") if rows
        else P("No audit entries found.", cls=MUTED),
        pagination_bar(page, total_pages, f"/audit?action_filter={action_filter}"),
    )
