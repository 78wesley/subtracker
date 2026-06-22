"""
layout.py — Page chrome styled with shadcn utility classes: nav bar, team switcher,
theme toggle, titles, cards, 403 page.
"""

from fasthtml.common import *

from app.components.widgets import alert, dropdown_menu, menu_item_cls
from app.permissions import Perm
from app.styles import (
    NAV,
    NAV_LINK,
    NAV_LINK_ACTIVE,
    PAGE_HEADER,
    SECTION,
    badge_cls,
    btn,
)


def _team_options(ctx) -> list:
    """(value, label, is_selected) for each team the caller can switch to.

    Super admins additionally get an 'All teams' (cross-team view) option."""
    options = []
    if ctx.is_super:
        options.append(("__all__", "🌐 All teams", ctx.view_all))
    for t in ctx.teams:
        options.append((str(t["id"]), t["name"],
                        (not ctx.view_all and t["id"] == ctx.active_team_id)))
    return options


def _team_switch_items(options) -> list:
    """The team options as POST-on-click DropdownMenu entries (one form each)."""
    return [
        Form(Button(lbl, type="submit", name="team_id", value=val,
                    cls=menu_item_cls(active=sel)),
             method="post", action="/teams/switch", cls="m-0")
        for val, lbl, sel in options
    ]


def team_switcher(ctx):
    """
    Active-team picker as a shadcn DropdownMenu (matching the Manage Actions menu).
    Super admins also get an 'All teams' option. Only rendered when there's an actual
    choice (>1 option); with a single team the name is shown as plain text instead.
    """
    if not ctx.teams:
        return Span("No team", cls=badge_cls("warn"))
    options = _team_options(ctx)
    if len(options) <= 1:
        return Span(ctx.active_team_name or ctx.teams[0]["name"],
                    cls="text-sm text-muted-foreground")
    current = next((lbl for _, lbl, sel in options if sel), options[0][1])
    return dropdown_menu(current, *_team_switch_items(options))


def theme_toggle() -> Button:
    """Light/dark switch — flips the `.dark` class on <html> (see THEME_JS)."""
    return Button(
        Span("🌙", cls="theme-icon-light"), Span("☀️", cls="theme-icon-dark"),
        cls=btn("outline", "icon"), type="button",
        onclick="toggleTheme()", title="Toggle light / dark theme",
        **{"aria-label": "Toggle light / dark theme"},
    )


# lucide menu (hamburger) — the mobile nav trigger.
_MENU_ICON = NotStr(
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round"><line x1="4" x2="20" y1="6" y2="6"/>'
    '<line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="18" y2="18"/></svg>'
)


def _nav_items(ctx) -> list:
    """[(label, href, key)] for the sections the current role may reach."""
    items = [
        ("Dashboard", "/dashboard", "dashboard", ctx.can(Perm.SUB_VIEW)),
        ("Manage", "/manage", "manage", ctx.can(Perm.SUB_VIEW)),
        ("Audit Log", "/audit", "audit", ctx.can(Perm.AUDIT_VIEW)),
        ("Teams", "/teams", "teams", ctx.can(Perm.TEAMS_MANAGE)),
        ("Deleted", "/admin/deleted", "deleted", ctx.can(Perm.RECORDS_VIEW_DELETED)),
        ("Users", "/users", "users", ctx.can(Perm.USERS_VIEW)),
    ]
    return [(lbl, href, key) for lbl, href, key, show in items if show]


def _sep():
    """A shadcn DropdownMenu separator, spanning the menu's inner padding."""
    return Div(cls="-mx-1 my-1 h-px bg-border", role="separator")


def _team_menu_items(ctx) -> list:
    """Team-switch options as DropdownMenu submit buttons (empty if no real choice)."""
    options = _team_options(ctx) if ctx.teams else []
    return _team_switch_items(options) if len(options) > 1 else []


def _mobile_menu(ctx, active: str, role_label: str):
    """Hamburger DropdownMenu holding the full nav for small screens."""
    items = [A(lbl, href=href, role="menuitem",
               cls=menu_item_cls(active=(key == active)))
             for lbl, href, key in _nav_items(ctx)]

    team_items = _team_menu_items(ctx)
    if team_items:
        items += [_sep(),
                  Div("Team", cls="px-2 pt-1 pb-0.5 text-xs font-medium text-muted-foreground"),
                  *team_items]

    items += [
        _sep(),
        Div(Div(f"👤 {ctx.username}", cls="text-sm font-medium truncate"),
            Div(role_label, cls="text-xs text-muted-foreground"),
            cls="px-2 py-1"),
        A("Logout", href="/logout", role="menuitem", cls=menu_item_cls()),
    ]
    return dropdown_menu(Span(_MENU_ICON, Span("Open menu", cls="sr-only")), *items)


def nav_bar(ctx, active: str = "") -> Nav:
    role_label = ctx.global_role.replace("_", " ").title()

    desktop_links = Div(
        *[A(lbl, href=href, cls=NAV_LINK_ACTIVE if key == active else NAV_LINK)
          for lbl, href, key in _nav_items(ctx)],
        cls="hidden md:flex items-center gap-x-5",
    )
    desktop_right = Div(
        team_switcher(ctx),
        Span(role_label, cls=badge_cls("secondary")),
        Span(f"👤 {ctx.username}", cls="text-sm text-muted-foreground"),
        theme_toggle(),
        A("Logout", href="/logout", cls=NAV_LINK),
        cls="hidden md:flex items-center gap-3",
    )

    return (
        Meta(name="csrf-token", content=ctx.csrf_token),
        Nav(
            A("💳 SubTracker", href="/dashboard", cls="font-bold text-base mr-1"),
            desktop_links,
            Div(cls="flex-1"),
            desktop_right,
            Div(theme_toggle(), _mobile_menu(ctx, active, role_label),
                cls="flex md:hidden items-center gap-2"),
            cls=NAV,
        ),
    )


def page_title(title: str) -> Title:
    return Title(f"{title} – SubTracker")


def forbidden_page(ctx, missing):
    """Friendly 'not authorized' page shown when a permission check fails."""
    needs = ", ".join(missing) if missing else "additional permissions"
    return page_title("Not allowed"), nav_bar(ctx), Main(
        Div(H2("🚫 Not authorized"), cls=PAGE_HEADER),
        alert(f"You don't have permission to do this (needs: {needs}). "
              "Ask a team admin or super admin for access.", "error"),
        P(A("← Back to dashboard", href="/dashboard")),
    )


def section_card(*children, heading: str = None) -> Div:
    inner = [H3(heading, cls="mb-3")] if heading else []
    inner += list(children)
    return Div(*inner, cls=SECTION)


def collapsible_card(heading: str, *children, open_: bool = False) -> Details:
    return Details(
        Summary(heading, cls="cursor-pointer font-semibold"),
        Div(*children, cls="mt-4"),
        cls=SECTION,
        **({"open": True} if open_ else {}),
    )
