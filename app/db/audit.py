"""
audit.py — Snapshot-based audit log: writes and queries.

Audit entries denormalise actor name, team name, and entity name at write time and
carry no foreign keys, so they remain accurate and queryable after the referenced
user / team / entity is permanently deleted.
"""

import json

from app import timeutil
from app.db.connection import get_db, rows_as_dicts
from app.permissions import Perm


def write_audit_log(actor_user_id: int, actor_name: str, action: str,
                    entity_type: str, entity_id: int, entity_name: str,
                    description: str, old_values=None, new_values=None,
                    actor_global_role: str | None = None,
                    team_id: int | None = None, team_name: str | None = None,
                    db=None) -> None:
    # Reuse the caller's connection when given one (e.g. a bulk import loop) instead
    # of opening a fresh SQLite connection per audited row.
    (db or get_db())["audit_log"].insert({
        "actor_user_id":     actor_user_id,
        "actor_name":        actor_name,
        "actor_global_role": actor_global_role,
        "team_id":           team_id,
        "team_name":         team_name,
        "action":            action,
        "entity_type":       entity_type,
        "entity_id":         entity_id,
        "entity_name":       entity_name,
        "old_values":        json.dumps(old_values) if old_values else None,
        "new_values":        json.dumps(new_values) if new_values else None,
        "description":       description,
        "timestamp":         timeutil.now_iso(),
    })


def audit(ctx, action: str, entity_type: str, entity_id: int, entity_name: str,
          description: str, old_values=None, new_values=None,
          team_id: int | None = None, team_name: str | None = None, db=None) -> None:
    """Convenience wrapper that snapshots actor + team from the request context.

    Pass `db` to reuse an open connection (e.g. inside a bulk-import loop)."""
    write_audit_log(
        ctx.user["id"], ctx.user["username"], action, entity_type, entity_id,
        entity_name, description, old_values=old_values, new_values=new_values,
        actor_global_role=ctx.user["global_role"],
        team_id=team_id if team_id is not None else ctx.active_team_id,
        team_name=team_name if team_name is not None else ctx.active_team_name, db=db)


def get_audit_for_entity(db, entity_id: int, entity_type: str) -> list:
    return rows_as_dicts(db,
        "SELECT * FROM audit_log WHERE entity_id = ? AND entity_type = ? "
        "ORDER BY timestamp DESC", [entity_id, entity_type])


def get_audit_log(db, ctx, action_filter: str | None = None,
                  page: int = 1, per_page: int = 25) -> tuple:
    """
    With audit.view: the active team's entries (all teams in super-admin view-all).
    Without it: only the caller's own actions.
    """
    where, params = [], []
    if Perm.AUDIT_VIEW in ctx.perms:
        if not (ctx.view_all and ctx.is_super):
            where.append("team_id = ?")
            params.append(ctx.active_team_id)
    else:
        where.append("actor_user_id = ?")
        params.append(ctx.user["id"])
    if action_filter:
        where.append("action = ?")
        params.append(action_filter)

    base = "SELECT * FROM audit_log"
    if where:
        base += " WHERE " + " AND ".join(where)
    total = db.execute(f"SELECT COUNT(*) FROM ({base})", params).fetchone()[0]
    query = base + f" ORDER BY timestamp DESC LIMIT {per_page} OFFSET {(page-1)*per_page}"
    return rows_as_dicts(db, query, params), total
