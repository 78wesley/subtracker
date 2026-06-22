"""
teams.py — Team and team-membership queries (live rows only).
"""

import re

from app import timeutil
from app.db.connection import one, rows_as_dicts

# ── Reads ────────────────────────────────────────────────────────────────────

def get_team(db, team_id: int):
    return one(db, "teams", "id = ? AND deleted_at IS NULL", [team_id])


def list_all_teams(db) -> list:
    return list(db["teams"].rows_where("deleted_at IS NULL", order_by="id"))


def list_user_teams(db, user_id: int) -> list:
    """Live teams the user belongs to, with their team_role."""
    return rows_as_dicts(db,
        "SELECT t.id, t.name, t.slug, tm.team_role "
        "FROM team_members tm JOIN teams t ON t.id = tm.team_id "
        "WHERE tm.user_id = ? AND tm.deleted_at IS NULL AND t.deleted_at IS NULL "
        "ORDER BY t.id", [user_id])


def get_membership(db, user_id: int, team_id: int):
    return one(db, "team_members",
               "user_id = ? AND team_id = ? AND deleted_at IS NULL", [user_id, team_id])


def list_team_members(db, team_id: int) -> list:
    return rows_as_dicts(db,
        "SELECT tm.id, tm.user_id, tm.team_role, u.username, u.global_role "
        "FROM team_members tm JOIN users u ON u.id = tm.user_id "
        "WHERE tm.team_id = ? AND tm.deleted_at IS NULL AND u.deleted_at IS NULL "
        "ORDER BY u.username COLLATE NOCASE", [team_id])


def count_team_admins(db, team_id: int) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM team_members WHERE team_id = ? "
        "AND team_role = 'team_admin' AND deleted_at IS NULL", [team_id]).fetchone()[0]


def member_count(db, team_id: int) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM team_members WHERE team_id = ? AND deleted_at IS NULL",
        [team_id]).fetchone()[0]


# ── Writes ───────────────────────────────────────────────────────────────────

def _slugify(db, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "team"
    slug, i = base, 2
    while one(db, "teams", "slug = ? AND deleted_at IS NULL", [slug]):
        slug, i = f"{base}-{i}", i + 1
    return slug


def create_team(db, name: str, description: str, created_by: int) -> int:
    now = timeutil.now_iso()
    return db["teams"].insert({
        "name": name, "slug": _slugify(db, name), "description": description or "",
        "created_at": now, "created_by": created_by,
    }).last_pk


def add_member(db, team_id: int, user_id: int, team_role: str, created_by: int) -> int:
    """Add or re-activate a membership; updates role if one already exists."""
    existing = get_membership(db, user_id, team_id)
    if existing:
        db["team_members"].update(existing["id"], {"team_role": team_role})
        return existing["id"]
    return db["team_members"].insert({
        "team_id": team_id, "user_id": user_id, "team_role": team_role,
        "created_at": timeutil.now_iso(), "created_by": created_by,
    }).last_pk


def set_member_role(db, membership_id: int, team_role: str) -> None:
    db["team_members"].update(membership_id, {"team_role": team_role})


def remove_member(db, membership_id: int, removed_by: int) -> None:
    db["team_members"].update(membership_id, {
        "deleted_at": timeutil.now_iso(), "deleted_by": removed_by})


def get_membership_by_id(db, membership_id: int):
    return one(db, "team_members", "id = ? AND deleted_at IS NULL", [membership_id])
