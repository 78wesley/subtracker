"""
app.db — stable import surface for all data access.

Route modules import from `app.db` so internal file moves stay invisible to handlers.
"""

from app.db.connection import get_db, rows_as_dicts, one
from app.db.schema import init_db, has_any_users
from app.db.users import (
    get_user_by_username, get_user_by_id, get_all_users, username_taken,
    count_super_admins, set_global_role, soft_delete_user,
)
from app.db.subscriptions import (
    get_subscription, get_active_subscriptions, get_all_subscriptions,
    get_categories, get_periods, get_periods_map, is_active_on, current_price,
    validate_periods, add_period, update_period, delete_period,
    restore_subscription, purge_subscription,
)
from app.db.teams import (
    get_team, list_all_teams, list_user_teams, get_membership, list_team_members,
    count_team_admins, member_count, create_team, add_member, set_member_role,
    remove_member, get_membership_by_id,
)
from app.db.roles import (
    permissions_for_role, list_roles, list_permissions, role_matrix, set_role_permission,
)
from app.db.audit import (
    write_audit_log, audit, get_audit_for_entity, get_audit_log,
)

__all__ = [
    "get_db", "rows_as_dicts", "one",
    "init_db", "has_any_users",
    "get_user_by_username", "get_user_by_id", "get_all_users", "username_taken",
    "count_super_admins", "set_global_role", "soft_delete_user",
    "get_subscription", "get_active_subscriptions", "get_all_subscriptions",
    "get_categories", "get_periods", "get_periods_map", "is_active_on",
    "current_price", "validate_periods", "add_period", "update_period",
    "delete_period", "restore_subscription", "purge_subscription",
    "get_team", "list_all_teams", "list_user_teams", "get_membership",
    "list_team_members", "count_team_admins", "member_count", "create_team",
    "add_member", "set_member_role", "remove_member", "get_membership_by_id",
    "permissions_for_role", "list_roles", "list_permissions", "role_matrix",
    "set_role_permission",
    "write_audit_log", "audit", "get_audit_for_entity", "get_audit_log",
]
