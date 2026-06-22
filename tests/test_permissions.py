"""The permission catalog and the Perm constants must stay in lock-step."""

from app.permissions import ALL_PERMISSIONS, PERMISSIONS, Perm
from app.rbac import ROLE_PERMISSIONS


def _perm_constants() -> set:
    return {v for k, v in vars(Perm).items()
            if not k.startswith("_") and isinstance(v, str)}


def test_constants_exactly_cover_the_catalog():
    assert _perm_constants() == set(ALL_PERMISSIONS)


def test_permission_names_are_unique():
    assert len(ALL_PERMISSIONS) == len(set(ALL_PERMISSIONS))
    assert len(PERMISSIONS) == len(ALL_PERMISSIONS)


def test_role_matrix_only_references_known_permissions():
    for role, perms in ROLE_PERMISSIONS.items():
        unknown = perms - set(ALL_PERMISSIONS)
        assert not unknown, f"{role} references unknown permissions: {unknown}"
