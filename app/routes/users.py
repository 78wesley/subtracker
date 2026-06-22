"""
users.py — Global user management: list, create (with global role), change role,
soft-delete. Gated on users.view (read) and users.manage (write).

Guards: cannot delete yourself, the last live user, or the last super admin; cannot
demote the last super admin; cannot change your own global role.
"""

from fasthtml.common import *

from app.authz import require
from app.components import alert, badge, nav_bar, page_title, select_menu
from app.db import (
    audit,
    count_super_admins,
    get_all_users,
    get_db,
    get_user_by_id,
    set_global_role,
    soft_delete_user,
    username_taken,
)
from app.permissions import Perm
from app.rbac import GLOBAL_ROLE_NAMES, global_role_rank
from app.styles import INPUT, MUTED, PAGE_HEADER, TABLE, btn

ar = APIRouter()

# Global role is binary: a normal account ("user") or a Super Admin.
_GLOBAL_ROLE_CHOICES = [("user", "User"), ("super_admin", "Super Admin")]
_ROLE_LABEL = dict(_GLOBAL_ROLE_CHOICES)
_FIELD = "grid gap-1.5 text-sm font-medium"


def _role_select(name: str, current: str, width: str = "w-[140px]"):
    return select_menu(name, _GLOBAL_ROLE_CHOICES, value=current, width=width)


@ar("/users")
def get(req, session, msg: str = "", msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.USERS_VIEW)): return r
    db = get_db()
    can_manage = ctx.can(Perm.USERS_MANAGE)
    all_users = get_all_users(db)

    def row(u):
        is_self = u["id"] == ctx.user["id"]
        if can_manage and not is_self:
            role_cell = Td(Form(
                _role_select("global_role", u["global_role"]),
                Button("Set", type="submit", cls=btn("outline", "sm")),
                method="post", action=f"/users/{u['id']}/role",
                cls="flex items-center gap-2 m-0",
            ))
            action_cell = Td(Form(
                Button("🗑️ Delete", cls=btn("outline", "sm"),
                       hx_post=f"/users/{u['id']}/delete",
                       hx_confirm=f"Delete user '{u['username']}'?",
                       hx_target="body", hx_push_url="/users"),
                method="post", cls="m-0",
            ), cls="nowrap")
        else:
            role_cell = Td(badge(_ROLE_LABEL.get(u["global_role"], u["global_role"]), "role"),
                           cls="nowrap")
            action_cell = Td(Span("(you)", cls=MUTED) if is_self else "", cls="nowrap")
        return Tr(
            Td(u["id"], cls="nowrap"),
            Td(u["username"], cls="font-medium"),
            role_cell,
            Td(u["created_at"][:16] if u["created_at"] else "—", cls="nowrap"),
            action_cell,
        )

    create_form = (
        Div(
            H3("Create New User", cls="mt-6 mb-3"),
            Form(
                Div(
                    Label("Username *", Input(name="username", required=True,
                          placeholder="username", cls=INPUT), cls=_FIELD),
                    Label("Password *", Input(name="password", type="password",
                          required=True, placeholder="password", cls=INPUT), cls=_FIELD),
                    Label("Global Role", _role_select("global_role", "user", "w-full"),
                          cls=_FIELD),
                    cls="grid gap-4 sm:grid-cols-3",
                ),
                Button("Create User", type="submit", cls=btn("outline") + " mt-4"),
                method="post", action="/users/new",
            ),
        ) if can_manage else ""
    )

    return page_title("Users"), nav_bar(ctx, "users"), Main(
        Div(H2("User Management"), cls=PAGE_HEADER),
        alert(msg, msg_kind) if msg else "",
        Div(Table(
            Thead(Tr(Th("ID"), Th("Username"), Th("Global Role"), Th("Created"), Th("Actions"))),
            Tbody(*[row(u) for u in all_users]), cls=TABLE,
        ), cls="rounded-xl border bg-card overflow-x-auto"),
        create_form,
    )


@ar("/users/new")
async def post(req, session, username: str, password: str, global_role: str = "user"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.USERS_MANAGE)): return r
    db = get_db()
    uname = username.strip()
    role = global_role if global_role in GLOBAL_ROLE_NAMES else "user"
    if not uname:
        return RedirectResponse("/users?msg=Username+cannot+be+empty", status_code=303)
    if global_role_rank(role) > global_role_rank(ctx.global_role):
        return RedirectResponse("/users?msg=Cannot+grant+a+role+above+your+own&msg_kind=error",
                                status_code=303)
    if username_taken(db, uname):
        return RedirectResponse("/users?msg=Username+already+exists", status_code=303)
    from app.auth import create_user
    uid = create_user(uname, password, global_role=role)
    audit(ctx, "CREATE", "user", uid, uname,
          f"Created user '{uname}' ({role})", new_values={"username": uname, "global_role": role})
    return RedirectResponse("/users", status_code=303)


@ar("/users/{uid}/role")
async def post(req, session, uid: int, global_role: str):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.USERS_MANAGE)): return r
    db = get_db()
    if uid == ctx.user["id"]:
        return RedirectResponse("/users?msg=Cannot+change+your+own+role", status_code=303)
    role = global_role if global_role in GLOBAL_ROLE_NAMES else None
    target = get_user_by_id(db, uid)
    if not target or role is None:
        return RedirectResponse("/users?msg=Invalid+role+or+user", status_code=303)
    actor_rank = global_role_rank(ctx.global_role)
    if global_role_rank(role) > actor_rank or global_role_rank(target["global_role"]) > actor_rank:
        return RedirectResponse("/users?msg=Cannot+manage+a+role+above+your+own&msg_kind=error",
                                status_code=303)
    if target["global_role"] == "super_admin" and role != "super_admin" \
            and count_super_admins(db) <= 1:
        return RedirectResponse("/users?msg=Cannot+demote+the+last+super+admin", status_code=303)
    old = target["global_role"]
    if old != role:
        set_global_role(db, uid, role)
        audit(ctx, "ROLE_CHANGE", "user", uid, target["username"],
              f"Changed {target['username']} role: {old} → {role}",
              old_values={"global_role": old}, new_values={"global_role": role})
    return RedirectResponse("/users", status_code=303)


@ar("/users/{uid}/delete")
async def post(req, session, uid: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.USERS_MANAGE)): return r
    db = get_db()
    if uid == ctx.user["id"]:
        return RedirectResponse("/users?msg=Cannot+delete+yourself", status_code=303)
    if len([u for u in get_all_users(db) if u["id"] != uid]) == 0:
        return RedirectResponse("/users?msg=Cannot+delete+the+last+user", status_code=303)
    target = get_user_by_id(db, uid)
    if target:
        if global_role_rank(target["global_role"]) > global_role_rank(ctx.global_role):
            return RedirectResponse("/users?msg=Cannot+delete+a+role+above+your+own&msg_kind=error",
                                    status_code=303)
        if target["global_role"] == "super_admin" and count_super_admins(db) <= 1:
            return RedirectResponse("/users?msg=Cannot+delete+the+last+super+admin", status_code=303)
        soft_delete_user(db, uid, ctx.user["id"])
        audit(ctx, "DELETE", "user", uid, target["username"],
              f"Deleted user '{target['username']}'",
              old_values={"deleted_at": None}, new_values={"deleted_by": ctx.user["id"]})
    return RedirectResponse("/users", status_code=303)
