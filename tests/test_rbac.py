"""Role-based access control: effective-permission resolution + context building."""

from app.auth import create_user
from app.db import create_team, add_member, get_user_by_id
from app.rbac import (
    resolve_permissions, build_ctx, can_access_team, ALL_PERMISSIONS, ROLE_PERMISSIONS,
)


def _user(db, uid):
    return dict(get_user_by_id(db, uid))


def test_super_admin_has_every_permission(db):
    uid = create_user("root", "pw", global_role="super_admin")
    perms = resolve_permissions(db, _user(db, uid), active_team_id=None, view_all=False)
    assert perms == set(ALL_PERMISSIONS)


def test_viewer_membership_grants_only_read(db):
    uid = create_user("vi", "pw", global_role="user")
    tid = create_team(db, "T", "", created_by=uid)
    add_member(db, tid, uid, "viewer", created_by=uid)
    perms = resolve_permissions(db, _user(db, uid), active_team_id=tid, view_all=False)
    assert perms == ROLE_PERMISSIONS["viewer"]
    assert "subscriptions.create" not in perms


def test_team_admin_membership_grants_management(db):
    uid = create_user("ta", "pw", global_role="user")
    tid = create_team(db, "T", "", created_by=uid)
    add_member(db, tid, uid, "team_admin", created_by=uid)
    perms = resolve_permissions(db, _user(db, uid), active_team_id=tid, view_all=False)
    assert "subscriptions.create" in perms
    assert "teams.manage" in perms


def test_baseline_user_without_team_has_no_perms(db):
    uid = create_user("nobody", "pw", global_role="user")
    perms = resolve_permissions(db, _user(db, uid), active_team_id=None, view_all=False)
    assert perms == set()


def test_perms_compose_by_union_only_for_active_team(db):
    """A user's team perms apply only to the team that is currently active."""
    uid = create_user("multi", "pw", global_role="user")
    t_admin = create_team(db, "AdminTeam", "", created_by=uid)
    t_view = create_team(db, "ViewTeam", "", created_by=uid)
    add_member(db, t_admin, uid, "team_admin", created_by=uid)
    add_member(db, t_view, uid, "viewer", created_by=uid)

    in_admin = resolve_permissions(db, _user(db, uid), t_admin, False)
    in_view = resolve_permissions(db, _user(db, uid), t_view, False)
    assert "subscriptions.create" in in_admin
    assert "subscriptions.create" not in in_view


def test_build_ctx_defaults_active_team_when_session_empty(db):
    uid = create_user("ta", "pw", global_role="user")
    tid = create_team(db, "T", "", created_by=uid)
    add_member(db, tid, uid, "team_admin", created_by=uid)
    session = {}
    ctx = build_ctx(db, _user(db, uid), session)
    assert ctx.active_team_id == tid
    assert session["active_team_id"] == tid          # written back into session
    assert ctx.can("subscriptions.create")


def test_build_ctx_ignores_team_user_cannot_access(db):
    uid = create_user("ta", "pw", global_role="user")
    mine = create_team(db, "Mine", "", created_by=uid)
    other = create_team(db, "Other", "", created_by=uid)  # uid is NOT a member
    add_member(db, mine, uid, "viewer", created_by=uid)
    ctx = build_ctx(db, _user(db, uid), {"active_team_id": other})
    assert ctx.active_team_id == mine                # fell back to an accessible team


def test_super_admin_can_access_any_team_member_cannot(db):
    admin = create_user("root", "pw", global_role="super_admin")
    member = create_user("m", "pw", global_role="user")
    tid = create_team(db, "T", "", created_by=admin)
    assert can_access_team(db, _user(db, admin), tid) is True
    assert can_access_team(db, _user(db, member), tid) is False
