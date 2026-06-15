"""
layout.py — Page chrome: role-aware nav bar, team switcher, titles, cards, 403 page.
"""

from fasthtml.common import *

from app import timeutil
from app.components.widgets import alert


def team_switcher(ctx):
    """Active-team <select> (auto-submits). Super admins also get an 'All teams' option."""
    if not ctx.teams:
        return Span("No team", cls="badge badge-warn")
    opts = []
    if ctx.is_super:
        opts.append(Option("🌐 All teams", value="__all__", selected=ctx.view_all))
    for t in ctx.teams:
        opts.append(Option(t["name"], value=str(t["id"]),
                           selected=(not ctx.view_all and t["id"] == ctx.active_team_id)))
    return Form(
        Select(*opts, name="team_id", onchange="this.form.submit()"),
        method="post", action="/teams/switch", cls="team-switch",
    )


def nav_bar(ctx, active: str = "") -> Nav:
    debug = timeutil.get_debug_date()
    debug_pill = Span(f"🕐 {debug}", cls="debug-pill") if debug else ""

    def link(label, href, key, show=True):
        if not show:
            return ""
        return A(label, href=href, cls="active" if key == active else None)

    role_label = ctx.global_role.replace("_", " ").title()

    return Nav(
        A("💳 SubTracker", href="/dashboard", cls="brand"),
        link("Dashboard", "/dashboard", "dashboard", ctx.can("subscriptions.view")),
        link("Manage", "/manage", "manage", ctx.can("subscriptions.view")),
        link("Audit Log", "/audit", "audit"),
        link("Teams", "/teams", "teams", ctx.can("teams.view")),
        link("Deleted", "/admin/deleted", "deleted", ctx.can("records.view_deleted")),
        link("Users", "/users", "users", ctx.can("users.view")),
        link("Roles", "/admin/roles", "roles", ctx.can("settings.manage")),
        link("Debug", "/debug", "debug", ctx.can("settings.manage")),
        debug_pill,
        Div(cls="spacer"),
        team_switcher(ctx),
        Span(role_label, cls="badge badge-role"),
        Span(f"👤 {ctx.username}", style="color:var(--pico-muted-color); font-size:.85rem;"),
        A("Logout", href="/logout"),
    )


def page_title(title: str) -> Title:
    return Title(f"{title} – SubTracker")


def forbidden_page(ctx, missing):
    """Friendly 'not authorized' page shown when a permission check fails."""
    needs = ", ".join(missing) if missing else "additional permissions"
    return page_title("Not allowed"), nav_bar(ctx), Main(
        Div(H2("🚫 Not authorized"), cls="page-header"),
        alert(f"You don't have permission to do this (needs: {needs}). "
              "Ask a team admin or super admin for access.", "error"),
        P(A("← Back to dashboard", href="/dashboard")),
    )


def section_card(*children, heading: str = None) -> Div:
    inner = [H3(heading)] if heading else []
    inner += list(children)
    return Div(*inner, cls="section-card")


def collapsible_card(heading: str, *children, open_: bool = False) -> Details:
    return Details(
        Summary(heading),
        *children,
        cls="section-card",
        **({"open": True} if open_ else {}),
    )
