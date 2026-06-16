"""
users.py — Global user management: list, create (with global role), change role,
soft-delete. Gated on users.view (read) and users.manage (write).

Guards: cannot delete yourself, the last live user, or the last super admin; cannot
demote the last super admin; cannot change your own global role.
"""

from fasthtml.common import *

from app.db import (
    get_db, get_all_users, get_user_by_id, username_taken,
    count_super_admins, set_global_role, soft_delete_user, audit,
)
from app.authz import require
from app.rbac import GLOBAL_ROLE_NAMES, global_role_rank
from app.components import page_title, nav_bar, alert, badge

ar = APIRouter()

# Global role is binary: a normal account ("user") or a Super Admin.
_GLOBAL_ROLE_CHOICES = [("user", "User"), ("super_admin", "Super Admin")]
_ROLE_LABEL = dict(_GLOBAL_ROLE_CHOICES)


def _role_select(name: str, current: str):
    return Select(*[Option(label, value=val, selected=(val == current))
                    for val, label in _GLOBAL_ROLE_CHOICES],
                  name=name)


@ar("/users")
def get(req, session, msg: str = "", msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "users.view")): return r
    db = get_db()
    can_manage = ctx.can("users.manage")
    all_users = get_all_users(db)

    def row(u):
        is_self = u["id"] == ctx.user["id"]
        if can_manage and not is_self:
            role_cell = Td(Form(
                _role_select("global_role", u["global_role"]),
                Button("Set", type="submit", cls="secondary outline",
                       style="padding:.2rem .6rem; font-size:.78rem; margin:0 0 0 .4rem"),
                method="post", action=f"/users/{u['id']}/role",
                style="display:flex; align-items:center; gap:.3rem; margin:0",
            ))
            action_cell = Td(Form(
                Button("🗑️ Delete", cls="secondary outline",
                       style="padding:.25rem .6rem; font-size:.8rem; margin:0",
                       hx_post=f"/users/{u['id']}/delete",
                       hx_confirm=f"Delete user '{u['username']}'?",
                       hx_target="body", hx_push_url="/users"),
                method="post",
            ), cls="nowrap")
        else:
            role_cell = Td(badge(_ROLE_LABEL.get(u["global_role"], u["global_role"]), "role"),
                           cls="nowrap")
            action_cell = Td(Span("(you)", style="color:var(--pico-muted-color)")
                             if is_self else "", cls="nowrap")
        return Tr(
            Td(u["id"], cls="nowrap"),
            Td(u["username"]),
            role_cell,
            Td(u["created_at"][:16] if u["created_at"] else "—", cls="nowrap"),
            action_cell,
        )

    create_form = (
        Div(
            H3("Create New User", style="margin-top:1.5rem"),
            Form(
                Grid(
                    Label("Username *", Input(name="username", required=True, placeholder="username")),
                    Label("Password *", Input(name="password", type="password",
                          required=True, placeholder="password")),
                    Label("Global Role", _role_select("global_role", "user")),
                ),
                Button("Create User", type="submit"),
                method="post", action="/users/new",
            ),
        ) if can_manage else ""
    )

    return page_title("Users"), nav_bar(ctx, "users"), Main(
        Div(H2("User Management"), cls="page-header"),
        alert(msg, msg_kind) if msg else "",
        Table(
            Thead(Tr(Th("ID"), Th("Username"), Th("Global Role"), Th("Created"), Th("Actions"))),
            Tbody(*[row(u) for u in all_users]),
        ),
        create_form,
    )


@ar("/users/new")
async def post(req, session, username: str, password: str, global_role: str = "user"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "users.manage")): return r
    db = get_db()
    uname = username.strip()
    role = global_role if global_role in GLOBAL_ROLE_NAMES else "user"
    if not uname:
        return RedirectResponse("/users?msg=Username+cannot+be+empty", status_code=303)
    # Rank ceiling: cannot create a user more powerful than yourself.
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
    if (r := require(ctx, "users.manage")): return r
    db = get_db()
    if uid == ctx.user["id"]:
        return RedirectResponse("/users?msg=Cannot+change+your+own+role", status_code=303)
    role = global_role if global_role in GLOBAL_ROLE_NAMES else None
    target = get_user_by_id(db, uid)
    if not target or role is None:
        return RedirectResponse("/users?msg=Invalid+role+or+user", status_code=303)
    # Rank ceiling: cannot assign, nor modify a user holding, a role above your own.
    actor_rank = global_role_rank(ctx.global_role)
    if global_role_rank(role) > actor_rank or global_role_rank(target["global_role"]) > actor_rank:
        return RedirectResponse("/users?msg=Cannot+manage+a+role+above+your+own&msg_kind=error",
                                status_code=303)
    # Don't demote the last remaining super admin.
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
    if (r := require(ctx, "users.manage")): return r
    db = get_db()
    if uid == ctx.user["id"]:
        return RedirectResponse("/users?msg=Cannot+delete+yourself", status_code=303)
    if len([u for u in get_all_users(db) if u["id"] != uid]) == 0:
        return RedirectResponse("/users?msg=Cannot+delete+the+last+user", status_code=303)
    target = get_user_by_id(db, uid)
    if target:
        # Rank ceiling: cannot delete a user more powerful than yourself.
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
