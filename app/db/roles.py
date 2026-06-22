"""
roles.py — Queries over the DB-driven roles / permissions / role_permissions tables.
"""



def permissions_for_role(db, role_name: str) -> set:
    return {r["permission_name"]
            for r in db["role_permissions"].rows_where("role_name = ?", [role_name])}


def list_roles(db, scope: str | None = None) -> list:
    where = "scope = ?" if scope else None
    args = [scope] if scope else None
    return list(db["roles"].rows_where(where, args, order_by="rank DESC"))


def list_permissions(db) -> list:
    return list(db["permissions"].rows)


def role_matrix(db) -> dict:
    """{role_name: set(permission_name)} across every role."""
    m: dict[str, set] = {}
    for r in db["role_permissions"].rows:
        m.setdefault(r["role_name"], set()).add(r["permission_name"])
    return m


def set_role_permission(db, role_name: str, permission_name: str, granted: bool) -> None:
    # Validate against the known catalogs so this helper can never write a junk
    # (role, permission) row even if a future caller passes unsanitised input.
    from app.rbac import ALL_PERMISSIONS, GLOBAL_ROLE_NAMES, TEAM_ROLE_NAMES
    if role_name not in (GLOBAL_ROLE_NAMES + TEAM_ROLE_NAMES):
        return
    if permission_name not in ALL_PERMISSIONS:
        return
    if granted:
        db["role_permissions"].upsert(
            {"role_name": role_name, "permission_name": permission_name},
            pk=("role_name", "permission_name"))
    else:
        db["role_permissions"].delete_where(
            "role_name = ? AND permission_name = ?", [role_name, permission_name])
