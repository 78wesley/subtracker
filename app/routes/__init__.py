"""
app.routes — collects every APIRouter so app.main can register them in one place.
"""

from app.routes import (
    auth_routes, dashboard, manage, subscriptions, import_export, audit_routes,
    users, teams, admin,
)

# Order is cosmetic; route paths are unique across modules.
ALL_ROUTERS = [
    auth_routes.ar,
    dashboard.ar,
    manage.ar,
    subscriptions.ar,
    import_export.ar,
    audit_routes.ar,
    users.ar,
    teams.ar,
    admin.ar,
]

__all__ = ["ALL_ROUTERS"]
