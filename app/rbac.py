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

from app.db.roles import permissions_for_role
from app.db.teams import get_membership, get_team, list_all_teams, list_user_teams


# ── Permission catalog (name, label, category) ───────────────────────────────

PERMISSIONS = [
    ("subscriptions.view",            "View subscriptions",            "Subscriptions"),
    ("subscriptions.create",          "Create subscriptions",          "Subscriptions"),
    ("subscriptions.edit",            "Edit subscriptions",            "Subscriptions"),
    ("subscriptions.delete",          "Delete (soft) subscriptions",   "Subscriptions"),
    ("subscriptions.delete.permanent","Permanently delete records",    "Subscriptions"),
    ("records.restore",               "Restore deleted records",       "Records"),
    ("records.view_deleted",          "View deleted records",          "Records"),
    ("teams.view",                    "View / switch teams",           "Teams"),
    ("teams.manage",                  "Manage teams & members",        "Teams"),
    ("users.view",                    "View users",                    "Users"),
    ("users.manage",                  "Manage users & global roles",   "Users"),
    ("audit.view",                    "View team audit log",           "Audit"),
    ("settings.manage",               "Manage settings & role matrix", "Settings"),
]
ALL_PERMISSIONS = [p[0] for p in PERMISSIONS]

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

_VIEWER = {"subscriptions.view", "teams.view"}

ROLE_PERMISSIONS = {
    "super_admin": set(ALL_PERMISSIONS),
    "team_admin":  _VIEWER | {"subscriptions.create", "subscriptions.edit",
                              "subscriptions.delete", "subscriptions.delete.permanent",
                              "records.restore", "records.view_deleted",
                              "teams.manage", "audit.view"},
    "viewer":      _VIEWER,
}


# ── Request context ──────────────────────────────────────────────────────────

class Ctx:
    """Per-request identity + authorization context, built by the Beforeware."""

    def __init__(self, user, active_team_id, active_team_name, teams, perms, view_all):
        self.user = user                      # users row (dict)
        self.active_team_id = active_team_id  # int | None
        self.active_team_name = active_team_name
        self.teams = teams                    # [{id, name, (team_role)}] the user may switch among
        self.perms = perms                    # set[str]
        self.view_all = view_all              # super_admin cross-team mode

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
    return Ctx(user, active, active_name, teams, perms, view_all)


def can_access_team(db, user: dict, team_id: int) -> bool:
    """May this user make `team_id` their active team?"""
    if user["global_role"] == "super_admin":
        return get_team(db, team_id) is not None
    return get_membership(db, user["id"], team_id) is not None
