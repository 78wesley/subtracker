"""
teams.py — Team list, active-team switching, team creation, member management,
and the super-admin cross-team "view all" toggle.

Member management requires teams.manage AND authority over the specific team
(global admin/super, or team_admin of that team).
"""

from fasthtml.common import *

from app.authz import require
from app.components import alert, badge, nav_bar, page_title, section_card, select_menu
from app.db import (
    add_member,
    audit,
    count_team_admins,
    create_team,
    get_all_users,
    get_db,
    get_membership,
    get_membership_by_id,
    get_team,
    get_user_by_id,
    list_all_teams,
    list_team_members,
    list_user_teams,
    member_count,
    remove_member,
    set_member_role,
)
from app.permissions import Perm
from app.rbac import TEAM_ROLE_NAMES, TEAM_ROLES, can_access_team
from app.styles import INPUT, LINK, MUTED, PAGE_HEADER, TABLE, btn

ar = APIRouter()

_TEAM_ROLE_LABEL = {name: label for name, label, _ in TEAM_ROLES}
_FIELD = "grid gap-1.5 text-sm font-medium"


def can_manage_team(db, ctx, team_id: int) -> bool:
    """Global admins manage any team; a team_admin manages only their own team."""
    if ctx.is_global_admin:
        return True
    m = get_membership(db, ctx.user["id"], team_id)
    return m is not None and m["team_role"] == "team_admin"


def _team_role_select(name: str, current: str = "viewer", width: str = "w-[130px]"):
    return select_menu(name, [(rname, label) for rname, label, _ in TEAM_ROLES],
                       value=current, width=width)


# ── Team list ────────────────────────────────────────────────────────────────

@ar("/teams")
def get(req, session, msg: str = "", msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_MANAGE)): return r
    db = get_db()
    can_create = ctx.can(Perm.TEAMS_MANAGE)

    teams = list_all_teams(db) if ctx.is_global_admin else list_user_teams(db, ctx.user["id"])
    rows = []
    for t in teams:
        tid = t["id"]
        role = t.get("team_role")
        is_active = (not ctx.view_all and tid == ctx.active_team_id)
        actions = [
            Form(Button("Switch", type="submit", cls=btn("outline", "sm")),
                 Input(type="hidden", name="team_id", value=str(tid)),
                 method="post", action="/teams/switch", cls="m-0 inline"),
        ]
        if can_manage_team(db, ctx, tid):
            actions.append(A("Members", href=f"/teams/{tid}/members",
                             role="button", cls=btn("outline", "sm")))
        rows.append(Tr(
            Td(Span(t["name"], cls="font-medium"),
               (" ", badge("active", "active")) if is_active else ""),
            Td(badge(_TEAM_ROLE_LABEL.get(role, role), "role") if role else "—", cls="nowrap"),
            Td(str(member_count(db, tid)), cls="nowrap"),
            Td(Div(*actions, cls="flex gap-2 flex-wrap"), cls="nowrap"),
        ))

    create_form = (
        section_card(
            heading="Create Team",
            *[Form(
                Div(
                    Label("Name *", Input(name="name", required=True,
                          placeholder="e.g. Marketing", cls=INPUT), cls=_FIELD),
                    Label("Description", Input(name="description", placeholder="optional",
                          cls=INPUT), cls=_FIELD),
                    cls="grid gap-4 sm:grid-cols-2",
                ),
                Button("Create Team", type="submit", cls=btn("outline") + " mt-4"),
                method="post", action="/teams/new",
            )],
        ) if can_create else ""
    )

    return page_title("Teams"), nav_bar(ctx, "teams"), Main(
        Div(H2("Teams"), cls=PAGE_HEADER),
        alert(msg, msg_kind) if msg else "",
        Div(Table(
            Thead(Tr(Th("Team"), Th("Your role"), Th("Members"), Th("Actions"))),
            Tbody(*rows), cls=TABLE,
        ), cls="rounded-xl border bg-card overflow-x-auto") if rows
        else P("You are not a member of any team yet.", cls=MUTED),
        create_form,
    )


# ── Switch active team / toggle view-all ─────────────────────────────────────

@ar("/teams/switch")
async def post(req, session, team_id: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_VIEW)): return r
    db = get_db()
    if team_id == "__all__" and ctx.is_super:
        session["view_all"] = True
        return RedirectResponse("/dashboard", status_code=303)
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return RedirectResponse("/teams?msg=Invalid+team", status_code=303)
    if not can_access_team(db, ctx.user, tid):
        return RedirectResponse("/teams?msg=No+access+to+that+team&msg_kind=error", status_code=303)
    session["view_all"] = False
    session["active_team_id"] = tid
    return RedirectResponse("/dashboard", status_code=303)


@ar("/teams/view-all")
async def post(req, session):
    ctx = req.scope["ctx"]
    if not ctx.is_super:
        return RedirectResponse("/dashboard", status_code=303)
    session["view_all"] = True
    return RedirectResponse("/dashboard", status_code=303)


# ── Create team ──────────────────────────────────────────────────────────────

@ar("/teams/new")
async def post(req, session, name: str, description: str = ""):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_MANAGE)): return r
    db = get_db()
    if not name.strip():
        return RedirectResponse("/teams?msg=Team+name+required", status_code=303)
    tid = create_team(db, name.strip(), description, created_by=ctx.user["id"])
    # Creator becomes team_admin so the team appears in their switcher with authority.
    add_member(db, tid, ctx.user["id"], "team_admin", created_by=ctx.user["id"])
    audit(ctx, "TEAM_CREATE", "team", tid, name.strip(),
          f"Created team '{name.strip()}'", team_id=tid, team_name=name.strip(),
          new_values={"name": name.strip()})
    session["active_team_id"] = tid
    session["view_all"] = False
    return RedirectResponse(f"/teams/{tid}/members", status_code=303)


# ── Member management ────────────────────────────────────────────────────────

@ar("/teams/{team_id}/members")
def get(req, session, team_id: int, msg: str = "", msg_kind: str = "warning"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_MANAGE)): return r
    db = get_db()
    team = get_team(db, team_id)
    if not team or not can_manage_team(db, ctx, team_id):
        return RedirectResponse("/teams?msg=No+access+to+manage+that+team&msg_kind=error",
                                status_code=303)

    members = list_team_members(db, team_id)
    member_ids = {m["user_id"] for m in members}

    member_rows = [
        Tr(
            Td(m["username"], cls="font-medium"),
            Td(badge(m["global_role"].replace("_", " ").title(), "secondary"), cls="nowrap"),
            Td(Form(
                _team_role_select("team_role", m["team_role"]),
                Button("Set", type="submit", cls=btn("outline", "sm")),
                method="post", action=f"/teams/{team_id}/members/{m['id']}/role",
                cls="flex items-center gap-2 m-0",
            )),
            Td(Form(
                Button("Remove", cls=btn("outline", "sm"),
                       hx_post=f"/teams/{team_id}/members/{m['id']}/remove",
                       hx_confirm=f"Remove {m['username']} from {team['name']}?",
                       hx_target="body", hx_push_url="true"),
                method="post", cls="m-0",
            ), cls="nowrap"),
        )
        for m in members
    ]

    addable = [u for u in get_all_users(db) if u["id"] not in member_ids]
    add_form = (
        section_card(
            heading="Add Member",
            *[Form(
                Div(
                    Label("User", select_menu("user_id",
                          [(str(u["id"]), u["username"]) for u in addable], width="w-full"),
                          cls=_FIELD),
                    Label("Team Role", _team_role_select("team_role", "viewer", "w-full"),
                          cls=_FIELD),
                    cls="grid gap-4 sm:grid-cols-2",
                ),
                Button("Add to Team", type="submit", cls=btn("outline") + " mt-4"),
                method="post", action=f"/teams/{team_id}/members/add",
            )],
        ) if addable else P("All users are already members of this team.", cls=MUTED)
    )

    return page_title(f"Members – {team['name']}"), nav_bar(ctx, "teams"), Main(
        Div(H2(f"Members: {team['name']}"), A("← Teams", href="/teams", cls=LINK), cls=PAGE_HEADER),
        alert(msg, msg_kind) if msg else "",
        Div(Table(
            Thead(Tr(Th("User"), Th("Global Role"), Th("Team Role"), Th("Actions"))),
            Tbody(*member_rows), cls=TABLE,
        ), cls="rounded-xl border bg-card overflow-x-auto") if member_rows
        else P("No members yet.", cls=MUTED),
        add_form,
    )


@ar("/teams/{team_id}/members/add")
async def post(req, session, team_id: int, user_id: int, team_role: str = "viewer"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_MANAGE)): return r
    db = get_db()
    team = get_team(db, team_id)
    if not team or not can_manage_team(db, ctx, team_id):
        return RedirectResponse("/teams?msg=No+access&msg_kind=error", status_code=303)
    role = team_role if team_role in TEAM_ROLE_NAMES else "viewer"
    target = get_user_by_id(db, user_id)
    if not target:
        return RedirectResponse(f"/teams/{team_id}/members?msg=Unknown+user", status_code=303)
    add_member(db, team_id, user_id, role, created_by=ctx.user["id"])
    audit(ctx, "MEMBER_ADD", "team", team_id, team["name"],
          f"Added {target['username']} to '{team['name']}' as {role}",
          team_id=team_id, team_name=team["name"],
          new_values={"user": target["username"], "team_role": role})
    return RedirectResponse(f"/teams/{team_id}/members", status_code=303)


@ar("/teams/{team_id}/members/{membership_id}/role")
async def post(req, session, team_id: int, membership_id: int, team_role: str):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_MANAGE)): return r
    db = get_db()
    team = get_team(db, team_id)
    if not team or not can_manage_team(db, ctx, team_id):
        return RedirectResponse("/teams?msg=No+access&msg_kind=error", status_code=303)
    m = get_membership_by_id(db, membership_id)
    role = team_role if team_role in TEAM_ROLE_NAMES else None
    if not m or m["team_id"] != team_id or role is None:
        return RedirectResponse(f"/teams/{team_id}/members?msg=Invalid", status_code=303)
    # Don't demote the last team admin.
    if m["team_role"] == "team_admin" and role != "team_admin" and count_team_admins(db, team_id) <= 1:
        return RedirectResponse(f"/teams/{team_id}/members?msg=Cannot+demote+the+last+team+admin"
                                "&msg_kind=error", status_code=303)
    if m["team_role"] != role:
        set_member_role(db, membership_id, role)
        audit(ctx, "ROLE_CHANGE", "team_member", membership_id, team["name"],
              f"Changed team role in '{team['name']}': {m['team_role']} → {role}",
              team_id=team_id, team_name=team["name"],
              old_values={"team_role": m["team_role"]}, new_values={"team_role": role})
    return RedirectResponse(f"/teams/{team_id}/members", status_code=303)


@ar("/teams/{team_id}/members/{membership_id}/remove")
async def post(req, session, team_id: int, membership_id: int):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.TEAMS_MANAGE)): return r
    db = get_db()
    team = get_team(db, team_id)
    if not team or not can_manage_team(db, ctx, team_id):
        return RedirectResponse("/teams?msg=No+access&msg_kind=error", status_code=303)
    m = get_membership_by_id(db, membership_id)
    if not m or m["team_id"] != team_id:
        return RedirectResponse(f"/teams/{team_id}/members?msg=Invalid", status_code=303)
    if m["team_role"] == "team_admin" and count_team_admins(db, team_id) <= 1:
        return RedirectResponse(f"/teams/{team_id}/members?msg=Cannot+remove+the+last+team+admin"
                                "&msg_kind=error", status_code=303)
    remove_member(db, membership_id, removed_by=ctx.user["id"])
    audit(ctx, "MEMBER_REMOVE", "team", team_id, team["name"],
          f"Removed a member from '{team['name']}'",
          team_id=team_id, team_name=team["name"])
    return RedirectResponse(f"/teams/{team_id}/members", status_code=303)
