"""
auth_routes.py — First-run setup, login, logout.
"""

from urllib.parse import quote_plus

from fasthtml.common import *

from app.auth import authenticate, create_user
from app.components import alert, page_title
from app.csrf import csrf_meta
from app.db import (
    add_member,
    create_team,
    get_db,
    get_user_by_id,
    has_any_users,
    init_db,
    write_audit_log,
)
from app.ratelimit import client_key, login_limiter
from app.styles import CARD, FIELD, INPUT, btn

ar = APIRouter()

_RATE_LIMIT_MSG = "Too many attempts. Wait a few minutes and try again."


# ── First-run setup (create initial admin) ───────────────────────────────────

@ar("/setup")
def get(session, error: str = ""):
    db = init_db()
    if has_any_users(db):
        return RedirectResponse("/login", status_code=303)
    return page_title("Setup"), csrf_meta(session), Titled("Welcome to SubTracker",
        Div(
            H2("Create your admin account", cls="mb-1"),
            alert(error, "error") if error else "",
            P("No users exist yet. Create the first account to get started.",
              cls="text-sm text-muted-foreground mb-4"),
            Form(
                Label("Username", Input(name="username", required=True,
                      placeholder="admin", autofocus=True, cls=INPUT), cls=FIELD),
                Label("Password", Input(type="password", name="password",
                      required=True, placeholder="choose a password", cls=INPUT), cls=FIELD),
                Label("Confirm Password", Input(type="password", name="password2",
                      required=True, placeholder="repeat password", cls=INPUT), cls=FIELD),
                Button("Create Account", type="submit", cls=btn("outline") + " w-full mt-1"),
                method="post", action="/setup", cls="grid gap-3",
            ),
            cls=CARD + " p-6 w-full max-w-sm mx-auto mt-12",
        )
    )


@ar("/setup")
async def post(req, session, username: str, password: str, password2: str):
    db = init_db()
    if has_any_users(db):
        return RedirectResponse("/login", status_code=303)
    if login_limiter.is_limited(client_key(req)):
        return RedirectResponse(f"/setup?error={quote_plus(_RATE_LIMIT_MSG)}", status_code=303)
    login_limiter.record(client_key(req))
    if not username.strip():
        return RedirectResponse("/setup?error=Username+cannot+be+empty", status_code=303)
    if password != password2:
        return RedirectResponse("/setup?error=Passwords+do+not+match", status_code=303)
    if len(password) < 6:
        return RedirectResponse("/setup?error=Password+must+be+at+least+6+characters", status_code=303)
    uname = username.strip()
    # First user is the Super Admin; give them a default team they administer.
    uid = create_user(uname, password, global_role="super_admin")
    team_id = create_team(db, "Default", "Default team", created_by=uid)
    add_member(db, team_id, uid, "team_admin", created_by=uid)
    write_audit_log(uid, uname, "CREATE", "user", uid, uname,
                    f"Super admin '{uname}' created during setup",
                    actor_global_role="super_admin", team_id=team_id, team_name="Default")
    session["user_id"] = uid
    session["active_team_id"] = team_id
    return RedirectResponse("/dashboard", status_code=303)


# ── Login / Logout ───────────────────────────────────────────────────────────

@ar("/")
def get(session):
    return RedirectResponse("/dashboard", status_code=303)


@ar("/login")
def get(session, error: str = ""):
    db = init_db()
    if not has_any_users(db):
        return RedirectResponse("/setup", status_code=303)
    return page_title("Login"), csrf_meta(session), Titled("SubTracker",
        Div(
            H2("Sign In", cls="mb-3"),
            alert(error, "error") if error else "",
            Form(
                Label("Username", Input(name="username", required=True,
                      placeholder="username", autofocus=True, cls=INPUT), cls=FIELD),
                Label("Password", Input(type="password", name="password",
                      required=True, placeholder="password", cls=INPUT), cls=FIELD),
                Button("Sign In", type="submit", cls=btn("outline") + " w-full mt-1"),
                method="post", action="/login", cls="grid gap-3",
            ),
            cls=CARD + " p-6 w-full max-w-sm mx-auto mt-12",
        )
    )


@ar("/login")
async def post(req, session, username: str, password: str):
    if login_limiter.is_limited(client_key(req)):
        return RedirectResponse(f"/login?error={quote_plus(_RATE_LIMIT_MSG)}", status_code=303)
    login_limiter.record(client_key(req))
    user = authenticate(username, password)
    if not user:
        return RedirectResponse("/login?error=Invalid+username+or+password", status_code=303)
    session["user_id"] = user["id"]
    write_audit_log(user["id"], user["username"], "LOGIN", "user", user["id"],
                    user["username"], f"User '{username}' logged in")
    return RedirectResponse("/dashboard", status_code=303)


@ar("/logout")
def get(session):
    uid = session.get("user_id")
    if uid:
        u = get_user_by_id(get_db(), uid)
        if u:
            write_audit_log(uid, u["username"], "LOGOUT", "user", uid, u["username"],
                            f"User '{u['username']}' logged out")
    session.clear()
    return RedirectResponse("/login", status_code=303)
