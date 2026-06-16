"""
admin.py — Admin tooling:
  • /admin/deleted   soft-deleted records: restore or permanently delete
  • /admin/roles     read-only reference of the three fixed roles and their permissions
"""

from fasthtml.common import *

from app.db import (
    get_db, get_all_subscriptions, get_subscription, get_all_users,
    restore_subscription, purge_subscription, audit,
)
from app.authz import require
from app.rbac import PERMISSIONS, ALL_PERMISSIONS, GLOBAL_ROLES, TEAM_ROLES, ROLE_PERMISSIONS
from app.components import (
    page_title, nav_bar, section_card, alert, badge, fmt_eur, category_label,
)

ar = APIRouter()


# ── Deleted records ──────────────────────────────────────────────────────────

@ar("/admin/deleted")
def get(req, session, msg: str = "", msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "records.view_deleted")): return r
    db = get_db()
    deleted = get_all_subscriptions(db, ctx, only_deleted=True)
    user_names = {u["id"]: u["username"] for u in get_all_users(db)}
    can_restore = ctx.can("records.restore")
    can_purge = ctx.can("subscriptions.delete.permanent")

    def actions(s):
        btns = []
        if can_restore:
            btns.append(Button("♻️ Restore", cls="secondary outline",
                        style="padding:.25rem .6rem; font-size:.8rem; margin:0",
                        hx_post=f"/admin/deleted/subscription/{s['id']}/restore",
                        hx_confirm=f"Restore '{s['name']}'?",
                        hx_target="body", hx_push_url="true"))
        if can_purge:
            btns.append(Button("🔥 Delete forever", cls="btn-danger",
                        style="padding:.25rem .6rem; font-size:.8rem; margin:0",
                        hx_post=f"/admin/deleted/subscription/{s['id']}/purge",
                        hx_confirm=f"PERMANENTLY delete '{s['name']}'? This cannot be undone.",
                        hx_target="body", hx_push_url="true"))
        return Div(*btns, style="display:flex; gap:.4rem; flex-wrap:wrap")

    rows = [
        Tr(
            Td(s["name"]),
            Td(badge(category_label(s.get("category")), "info"), cls="nowrap"),
            Td(fmt_eur(s["amount"]), cls="nowrap"),
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
                      style="color:var(--pico-muted-color)")),
            cls="page-header"),
        alert(msg, msg_kind) if msg else "",
        P(Small("Soft-deleted subscriptions remain hidden from normal views. "
                "Audit history is preserved even after permanent deletion.")),
        Table(
            Thead(Tr(Th("Name"), Th("Category"), Th("Amount"),
                     Th("Deleted At"), Th("Deleted By"), Th("Actions"))),
            Tbody(*rows),
        ) if rows else P("No deleted records."),
    )


@ar("/admin/deleted/subscription/{sub_id}/restore")
async def post(req, session, sub_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "records.restore")): return r
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
    if (r := require(ctx, "subscriptions.delete.permanent")): return r
    db = get_db()
    sub = get_subscription(db, ctx, sub_id, include_deleted=True)
    if not sub:
        return RedirectResponse("/admin/deleted", status_code=303)
    # Snapshot into the audit log BEFORE the row is gone (audit has no FK to it).
    audit(ctx, "PERMANENT_DELETE", "subscription", sub_id, sub["name"],
          f"Permanently deleted '{sub['name']}' (€{sub['amount']}, {sub.get('category') or '—'})",
          old_values={"name": sub["name"], "amount": sub["amount"],
                      "category": sub.get("category"), "frequency": sub.get("frequency")})
    purge_subscription(db, sub_id)
    return RedirectResponse("/admin/deleted?msg=Record+permanently+deleted&msg_kind=success",
                            status_code=303)


# ── Roles reference (read-only) ──────────────────────────────────────────────

_MATRIX_ROLES = [(n, l) for n, l, _ in GLOBAL_ROLES] + [(n, l) for n, l, _ in TEAM_ROLES]
_ROLE_SCOPE = {"super_admin": "Global", "team_admin": "Team", "viewer": "Team"}


@ar("/admin/roles")
def get(req, session):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "settings.manage")): return r

    perm_label = {p[0]: p[1] for p in PERMISSIONS}
    perm_cat = {p[0]: p[2] for p in PERMISSIONS}

    def cell(role, perm):
        held = perm in ROLE_PERMISSIONS.get(role, set())
        return Td("✓" if held else "—", cls="nowrap",
                  style=f"text-align:center; color:{'var(--pico-primary)' if held else 'var(--pico-muted-color)'}")

    rows, last_cat = [], None
    for perm in ALL_PERMISSIONS:
        if perm_cat[perm] != last_cat:
            last_cat = perm_cat[perm]
            rows.append(Tr(Td(Strong(last_cat), colspan=str(len(_MATRIX_ROLES) + 1),
                              style="background:var(--pico-muted-border-color)")))
        rows.append(Tr(
            Td(perm_label[perm], Br(), Small(perm, style="color:var(--pico-muted-color)")),
            *[cell(role, perm) for role, _ in _MATRIX_ROLES],
        ))

    legend = P(*[Span(badge(label, "role"), " ",
                      Small(f"({_ROLE_SCOPE[name]})  ", style="color:var(--pico-muted-color)"))
                 for name, label in _MATRIX_ROLES])

    return page_title("Roles"), nav_bar(ctx, "roles"), Main(
        Div(H2("Roles & Permissions"), cls="page-header"),
        P("Roles are fixed. Assign a ", Strong("global role"), " (User / Super Admin) on the ",
          A("Users", href="/users"), " page, and a ", Strong("team role"),
          " (Team Admin / Viewer) on each team's ", A("Members", href="/teams"), " page."),
        section_card(
            legend,
            Table(
                Thead(Tr(Th("Permission"), *[Th(label, cls="nowrap") for _, label in _MATRIX_ROLES])),
                Tbody(*rows),
            ),
        ),
    )
