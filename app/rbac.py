"""
rbac.py — Role-based access control: permission catalog, role→permission matrix,
request context (Ctx), and effective-permission resolution.

Design
------
Two role axes that COMPOSE BY UNION:
  * global role (users.global_role): super_admin > admin > user
  * team role  (team_members.team_role): team_admin > manager > viewer
Effective perms for a (user, active_team) pair = global-role perms ∪ team-role perms
(team perms only if a live membership exists). super_admin = ALL permissions.

Role→permission mappings are seeded into the role_permissions table from the
constants below, so they are editable in the DB without code changes (spec §8).
Permission STRINGS are fixed in code because enforcement references them.
"""

from app.csrf import ensure_token
from app.db.roles import permissions_for_role
from app.db.teams import get_membership, get_team, list_all_teams, list_user_teams

# Re-exported so existing `from app.rbac import Perm, PERMISSIONS, ALL_PERMISSIONS`
# imports keep working; the catalog itself lives in the dependency-free module.
from app.permissions import ALL_PERMISSIONS, PERMISSIONS, Perm

# `PERMISSIONS` is consumed by importers (e.g. app.db.seed), not by this module —
# declaring it here marks the re-export as intentional.
__all__ = [
    "ALL_PERMISSIONS", "PERMISSIONS", "Perm", "ROLE_PERMISSIONS",
    "GLOBAL_ROLES", "TEAM_ROLES", "GLOBAL_ROLE_NAMES", "TEAM_ROLE_NAMES",
    "CANONICAL_ROLE_NAMES", "BASELINE_GLOBAL_ROLE", "Ctx", "build_ctx",
    "resolve_permissions", "can_access_team", "global_role_rank",
]

# ── Roles (name, label, rank) ────────────────────────────────────────────────
# Exactly three assignable roles exist, with fixed (non-editable) permission sets:
#   • super_admin — global; runs everything across all teams
#   • team_admin  — per team; full management of their team (subs + members)
#   • viewer      — per team; read-only
# 'user' is the implicit baseline for a normal account (no global powers, no
# permissions of its own) — a valid stored value, but not a seeded/assignable role.

GLOBAL_ROLES = [("super_admin", "Super Admin", 100)]
TEAM_ROLES   = [("team_admin", "Team Admin", 70), ("viewer", "Viewer", 30)]

BASELINE_GLOBAL_ROLE = "user"
GLOBAL_ROLE_NAMES = ["super_admin", BASELINE_GLOBAL_ROLE]
TEAM_ROLE_NAMES   = [r[0] for r in TEAM_ROLES]

# Every role name that is a real, seeded role with a permission set.
CANONICAL_ROLE_NAMES = [r[0] for r in GLOBAL_ROLES] + TEAM_ROLE_NAMES

_GLOBAL_ROLE_RANK = {"super_admin": 100, BASELINE_GLOBAL_ROLE: 10}


def global_role_rank(role: str) -> int:
    """Authority rank of a global role (higher = stronger); unknown roles rank 0."""
    return _GLOBAL_ROLE_RANK.get(role, 0)

# ── Fixed role → permission sets (source of truth for seeding) ───────────────

_VIEWER = {Perm.SUB_VIEW, Perm.TEAMS_VIEW}

ROLE_PERMISSIONS = {
    "super_admin": set(ALL_PERMISSIONS),
    "team_admin":  _VIEWER | {Perm.SUB_CREATE, Perm.SUB_EDIT,
                              Perm.SUB_DELETE, Perm.SUB_DELETE_PERMANENT,
                              Perm.RECORDS_RESTORE, Perm.RECORDS_VIEW_DELETED,
                              Perm.TEAMS_MANAGE, Perm.AUDIT_VIEW},
    "viewer":      _VIEWER,
}


# ── Request context ──────────────────────────────────────────────────────────

class Ctx:
    """Per-request identity + authorization context, built by the Beforeware."""

    def __init__(self, user, active_team_id, active_team_name, teams, perms, view_all,
                 csrf_token=""):
        self.user = user                      # users row (dict)
        self.active_team_id = active_team_id  # int | None
        self.active_team_name = active_team_name
        self.teams = teams                    # [{id, name, (team_role)}] the user may switch among
        self.perms = perms                    # set[str]
        self.view_all = view_all              # super_admin cross-team mode
        self.csrf_token = csrf_token          # per-session CSRF token (for <meta>)

    @property
    def username(self):
        return self.user["username"]

    @property
    def global_role(self):
        return self.user["global_role"]

    @property
    def is_super(self):
        return self.global_role == "super_admin"

    @property
    def is_global_admin(self):
        return self.global_role == "super_admin"

    def can(self, perm: str) -> bool:
        return perm in self.perms


# ── Resolution ───────────────────────────────────────────────────────────────

def resolve_permissions(db, user: dict, active_team_id, view_all: bool) -> set:
    role = user["global_role"]
    if role == "super_admin":
        return set(ALL_PERMISSIONS)
    perms = set(permissions_for_role(db, role))
    if active_team_id is not None:
        m = get_membership(db, user["id"], active_team_id)
        if m:
            perms |= permissions_for_role(db, m["team_role"])
    return perms


def build_ctx(db, user: dict, session: dict) -> Ctx:
    """Resolve the active team + effective permissions for this request."""
    view_all = bool(session.get("view_all")) and user["global_role"] == "super_admin"

    # Teams the user may operate on / switch among.
    if user["global_role"] == "super_admin":
        teams = [dict(t) for t in list_all_teams(db)]      # super admin reaches every team
    else:
        teams = list_user_teams(db, user["id"])            # members reach their teams

    team_ids = [t["id"] for t in teams]
    active = session.get("active_team_id")
    if active not in team_ids:
        active = team_ids[0] if team_ids else None
        session["active_team_id"] = active
    active_name = next((t["name"] for t in teams if t["id"] == active), None)

    perms = resolve_permissions(db, user, active, view_all)
    return Ctx(user, active, active_name, teams, perms, view_all,
               csrf_token=ensure_token(session))


def can_access_team(db, user: dict, team_id: int) -> bool:
    """May this user make `team_id` their active team?"""
    if user["global_role"] == "super_admin":
        return get_team(db, team_id) is not None
    return get_membership(db, user["id"], team_id) is not None
