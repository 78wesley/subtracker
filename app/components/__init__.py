"""
app.components — stable import surface for all shared UI primitives.
"""

from app.components.charts import bar_chart, hbar_breakdown, line_chart
from app.components.fmt import (
    MONTH_LABELS,
    category_label,
    fmt_eur,
    json_pretty,
    truncate,
)
from app.components.forms import subscription_form
from app.components.layout import (
    collapsible_card,
    forbidden_page,
    nav_bar,
    page_title,
    section_card,
    team_switcher,
)
from app.components.widgets import (
    action_btn,
    action_menu,
    alert,
    badge,
    dropdown_menu,
    menu_item_cls,
    pagination_bar,
    select_menu,
    status_badge,
)

__all__ = [
    "MONTH_LABELS", "fmt_eur", "category_label", "truncate", "json_pretty",
    "alert", "badge", "status_badge", "action_btn", "action_menu", "pagination_bar",
    "dropdown_menu", "menu_item_cls", "select_menu",
    "nav_bar", "page_title", "section_card", "collapsible_card",
    "team_switcher", "forbidden_page",
    "bar_chart", "line_chart", "hbar_breakdown", "subscription_form",
]
