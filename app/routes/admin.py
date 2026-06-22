"""
admin.py — Admin tooling:
  • /admin/deleted   soft-deleted records: restore or permanently delete
"""

from fasthtml.common import *

from app.authz import require
from app.components import (
    alert,
    badge,
    category_label,
    fmt_eur,
    nav_bar,
    page_title,
)
from app.db import (
    audit,
    current_price,
    get_all_subscriptions,
    get_all_users,
    get_db,
    get_periods,
    get_periods_map,
    get_subscription,
    purge_subscription,
    restore_subscription,
)
from app.permissions import Perm
from app.styles import MUTED, PAGE_HEADER, TABLE, btn

ar = APIRouter()


# ── Deleted records ──────────────────────────────────────────────────────────

@ar("/admin/deleted")
def get(req, session, msg: str = "", msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.RECORDS_VIEW_DELETED)): return r
    db = get_db()
    deleted = get_all_subscriptions(db, ctx, only_deleted=True)
    periods_map = get_periods_map(db, [s["id"] for s in deleted])
    user_names = {u["id"]: u["username"] for u in get_all_users(db)}
    can_restore = ctx.can(Perm.RECORDS_RESTORE)
    can_purge = ctx.can(Perm.SUB_DELETE_PERMANENT)

    def actions(s):
        btns = []
        if can_restore:
            btns.append(Button("♻️ Restore", cls=btn("outline", "sm"),
                        hx_post=f"/admin/deleted/subscription/{s['id']}/restore",
                        hx_confirm=f"Restore '{s['name']}'?",
                        hx_target="body", hx_push_url="true"))
        if can_purge:
            btns.append(Button("🔥 Delete forever", cls=btn("destructive", "sm"),
                        hx_post=f"/admin/deleted/subscription/{s['id']}/purge",
                        hx_confirm=f"PERMANENTLY delete '{s['name']}'? This cannot be undone.",
                        hx_target="body", hx_push_url="true"))
        return Div(*btns, cls="flex gap-2 flex-wrap")

    rows = [
        Tr(
            Td(s["name"], cls="font-medium"),
            Td(badge(category_label(s.get("category")), "info"), cls="nowrap"),
            Td((lambda pr: fmt_eur(pr) if pr is not None else "—")(
                current_price(periods_map.get(s["id"], []))), cls="nowrap"),
            Td((s["deleted_at"] or "")[:16], cls="nowrap"),
            Td(user_names.get(s.get("deleted_by"), f"#{s.get('deleted_by')}"
               if s.get("deleted_by") else "—"), cls="nowrap"),
            Td(actions(s), cls="nowrap"),
        )
        for s in deleted
    ]

    return page_title("Deleted Records"), nav_bar(ctx, "deleted"), Main(
        Div(H2("Deleted Records ",
                Small(f"· {'all teams' if (ctx.view_all and ctx.is_super) else (ctx.active_team_name or 'no team')}",
                      cls="text-muted-foreground font-normal")),
            cls=PAGE_HEADER),
        alert(msg, msg_kind) if msg else "",
        P(Small("Soft-deleted subscriptions remain hidden from normal views. "
                "Audit history is preserved even after permanent deletion.", cls=MUTED)),
        Div(Table(
            Thead(Tr(Th("Name"), Th("Category"), Th("Amount"),
                     Th("Deleted At"), Th("Deleted By"), Th("Actions"))),
            Tbody(*rows), cls=TABLE,
        ), cls="rounded-xl border bg-card overflow-x-auto mt-3") if rows
        else P("No deleted records.", cls=MUTED),
    )


@ar("/admin/deleted/subscription/{sub_id}/restore")
async def post(req, session, sub_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.RECORDS_RESTORE)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id, include_deleted=True)
    if not sub or sub.get("deleted_at") is None:
        return RedirectResponse("/admin/deleted", status_code=303)
    restore_subscription(db, sub_id)
    audit(ctx, "RESTORE", "subscription", sub_id, sub["name"],
          f"Restored '{sub['name']}'",
          old_values={"deleted_at": sub["deleted_at"]}, new_values={"deleted_at": None})
    return RedirectResponse("/admin/deleted", status_code=303)


@ar("/admin/deleted/subscription/{sub_id}/purge")
async def post(req, session, sub_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_DELETE_PERMANENT)): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id, include_deleted=True)
    if not sub:
        return RedirectResponse("/admin/deleted", status_code=303)
    # Snapshot into the audit log BEFORE the row is gone (audit has no FK to it).
    price = current_price(get_periods(db, sub_id))
    audit(ctx, "PERMANENT_DELETE", "subscription", sub_id, sub["name"],
          f"Permanently deleted '{sub['name']}' "
          f"({fmt_eur(price) if price is not None else '—'}, {sub.get('category') or '—'})",
          old_values={"name": sub["name"], "amount": price,
                      "category": sub.get("category"), "frequency": sub.get("frequency")})
    purge_subscription(db, sub_id)
    return RedirectResponse("/admin/deleted?msg=Record+permanently+deleted&msg_kind=success",
                            status_code=303)
