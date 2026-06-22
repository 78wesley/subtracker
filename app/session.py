"""
session.py — Beforeware that authenticates and builds the request context.

`load_ctx` runs before every non-skipped route: it redirects to /setup when no
users exist and to /login when not authenticated, otherwise it stashes a fully
resolved `Ctx` (user, active team, effective permissions) on `req.scope["ctx"]`.
"""

from starlette.responses import RedirectResponse

from app.db import get_db, get_user_by_id, has_any_users
from app.rbac import build_ctx

# Paths the auth gate does NOT run on (public pages + top-level static assets).
# The asset pattern is anchored to a single top-level segment so it can never
# match a nested application route that happens to end in one of these suffixes.
SKIP = [
    r"/login", r"/setup", r"/logout", r"/favicon\.ico",
    r"/[^/]*\.(css|js|ico|png|jpe?g|svg|woff2?|map|txt)",
]


def load_ctx(req, session):
    # Schema is created at startup (app.main) and by /setup, /login; this gate
    # only needs to read, so it avoids the per-request init/seed cost.
    db = get_db()
    if not has_any_users(db):
        return RedirectResponse("/setup", status_code=303)
    uid = session.get("user_id")
    user = get_user_by_id(db, uid) if uid else None
    if not user:
        session.clear()
        return RedirectResponse("/login", status_code=303)
    req.scope["ctx"] = build_ctx(db, user, session)


def current_user(session: dict):
    uid = session.get("user_id")
    return get_user_by_id(get_db(), uid) if uid else None
