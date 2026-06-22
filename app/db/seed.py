"""
seed.py — Idempotent seeding of the RBAC reference data (the three fixed roles,
the permission catalog, and the fixed role→permission matrix). Safe on every boot.

Also clamps any legacy data (old 'admin'/'manager' roles from earlier versions) to
the canonical set so the model stays exactly three roles.
"""

from app.rbac import (
    CANONICAL_ROLE_NAMES,
    GLOBAL_ROLE_NAMES,
    GLOBAL_ROLES,
    PERMISSIONS,
    ROLE_PERMISSIONS,
    TEAM_ROLE_NAMES,
    TEAM_ROLES,
)


def seed_rbac(db) -> None:
    for name, label, category in PERMISSIONS:
        db["permissions"].upsert({"name": name, "label": label, "category": category}, pk="name")

    for name, label, rank in GLOBAL_ROLES:
        db["roles"].upsert({"name": name, "scope": "global", "label": label,
                            "is_system": 1, "rank": rank}, pk="name")
    for name, label, rank in TEAM_ROLES:
        db["roles"].upsert({"name": name, "scope": "team", "label": label,
                            "is_system": 1, "rank": rank}, pk="name")

    # Roles have FIXED permission sets: make the matrix match the source of truth
    # exactly (replace, not merely add) so it can never drift.
    db.execute("DELETE FROM role_permissions")
    for role_name, perms in ROLE_PERMISSIONS.items():
        for perm in perms:
            db["role_permissions"].insert({"role_name": role_name, "permission_name": perm})

    _clamp_legacy_roles(db)
    db.conn.commit()


def _clamp_legacy_roles(db) -> None:
    """Map any pre-existing non-canonical role values onto the three-role model."""
    # Legacy global 'admin' (or anything unexpected) → baseline 'user'.
    db.execute(
        "UPDATE users SET global_role = 'user' WHERE global_role NOT IN (?, ?)",
        GLOBAL_ROLE_NAMES)
    # Legacy team 'manager' (or anything unexpected) → least-privilege 'viewer'.
    db.execute(
        "UPDATE team_members SET team_role = 'viewer' WHERE team_role NOT IN (?, ?)",
        TEAM_ROLE_NAMES)
    # Drop role rows that are no longer part of the model.
    placeholders = ", ".join("?" for _ in CANONICAL_ROLE_NAMES)
    db.execute(f"DELETE FROM roles WHERE name NOT IN ({placeholders})", CANONICAL_ROLE_NAMES)
