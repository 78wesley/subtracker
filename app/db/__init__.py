"""
app.db — stable import surface for all data access.

Route modules import from `app.db` so internal file moves stay invisible to handlers.
"""

from app.db.audit import (
    audit,
    get_audit_for_entity,
    get_audit_log,
    write_audit_log,
)
from app.db.connection import get_db, one, rows_as_dicts
from app.db.roles import (
    list_permissions,
    list_roles,
    permissions_for_role,
    role_matrix,
    set_role_permission,
)
from app.db.schema import has_any_users, init_db
from app.db.subscriptions import (
    add_period,
    current_price,
    delete_period,
    get_active_subscriptions,
    get_all_subscriptions,
    get_categories,
    get_periods,
    get_periods_map,
    get_subscription,
    is_active_on,
    purge_subscription,
    restore_subscription,
    upcoming_price_change,
    update_period,
    validate_periods,
)
from app.db.teams import (
    add_member,
    count_team_admins,
    create_team,
    get_membership,
    get_membership_by_id,
    get_team,
    list_all_teams,
    list_team_members,
    list_user_teams,
    member_count,
    remove_member,
    set_member_role,
)
from app.db.users import (
    count_super_admins,
    get_all_users,
    get_user_by_id,
    get_user_by_username,
    set_global_role,
    soft_delete_user,
    username_taken,
)

__all__ = [
    "get_db", "rows_as_dicts", "one",
    "init_db", "has_any_users",
    "get_user_by_username", "get_user_by_id", "get_all_users", "username_taken",
    "count_super_admins", "set_global_role", "soft_delete_user",
    "get_subscription", "get_active_subscriptions", "get_all_subscriptions",
    "get_categories", "get_periods", "get_periods_map", "is_active_on",
    "current_price", "upcoming_price_change", "validate_periods", "add_period",
    "update_period", "delete_period", "restore_subscription", "purge_subscription",
    "get_team", "list_all_teams", "list_user_teams", "get_membership",
    "list_team_members", "count_team_admins", "member_count", "create_team",
    "add_member", "set_member_role", "remove_member", "get_membership_by_id",
    "permissions_for_role", "list_roles", "list_permissions", "role_matrix",
    "set_role_permission",
    "write_audit_log", "audit", "get_audit_for_entity", "get_audit_log",
]
