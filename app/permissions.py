"""
permissions.py — The permission catalog: names, labels, categories.

Kept dependency-free (imports nothing from `app`) so any layer — routes, data
helpers, the RBAC resolver — can reference `Perm` without risking a circular
import. `Perm` is the single source of truth for permission NAMES: code uses the
constants (a typo becomes an AttributeError at import time rather than a silent
allow/deny), while the string VALUES stay stable for the DB role matrix.
"""


class Perm:
    SUB_VIEW             = "subscriptions.view"
    SUB_CREATE           = "subscriptions.create"
    SUB_EDIT             = "subscriptions.edit"
    SUB_DELETE           = "subscriptions.delete"
    SUB_DELETE_PERMANENT = "subscriptions.delete.permanent"
    RECORDS_RESTORE      = "records.restore"
    RECORDS_VIEW_DELETED = "records.view_deleted"
    TEAMS_VIEW           = "teams.view"
    TEAMS_MANAGE         = "teams.manage"
    USERS_VIEW           = "users.view"
    USERS_MANAGE         = "users.manage"
    AUDIT_VIEW           = "audit.view"
    SETTINGS_MANAGE      = "settings.manage"


# (name, label, category) for each permission, in display order.
PERMISSIONS = [
    (Perm.SUB_VIEW,             "View subscriptions",            "Subscriptions"),
    (Perm.SUB_CREATE,           "Create subscriptions",          "Subscriptions"),
    (Perm.SUB_EDIT,             "Edit subscriptions",            "Subscriptions"),
    (Perm.SUB_DELETE,           "Delete (soft) subscriptions",   "Subscriptions"),
    (Perm.SUB_DELETE_PERMANENT, "Permanently delete records",    "Subscriptions"),
    (Perm.RECORDS_RESTORE,      "Restore deleted records",       "Records"),
    (Perm.RECORDS_VIEW_DELETED, "View deleted records",          "Records"),
    (Perm.TEAMS_VIEW,           "View / switch teams",           "Teams"),
    (Perm.TEAMS_MANAGE,         "Manage teams & members",        "Teams"),
    (Perm.USERS_VIEW,           "View users",                    "Users"),
    (Perm.USERS_MANAGE,         "Manage users & global roles",   "Users"),
    (Perm.AUDIT_VIEW,           "View team audit log",           "Audit"),
    (Perm.SETTINGS_MANAGE,      "Manage settings & role matrix", "Settings"),
]
ALL_PERMISSIONS = [p[0] for p in PERMISSIONS]
