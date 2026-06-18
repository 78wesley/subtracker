"""
dashboard.py — Spend dashboard: cost cards, monthly chart, breakdowns.
"""

from fasthtml.common import *

from app import timeutil
from app.db import get_db, get_all_subscriptions, get_periods_map
from app.authz import require
from app.cost_utils import (
    year_cost, monthly_costs_for_year, frequency_label,
)
from app.components import (
    page_title, nav_bar, section_card, fmt_eur, category_label,
    bar_chart, hbar_breakdown, MONTH_LABELS,
)
from app.styles import (
    PAGE_HEADER, COST_CARD, COST_CARDS, COST_LABEL, COST_AMOUNT,
    CHARTS_GRID, LINK, btn,
)

ar = APIRouter()


def _year_analytics(db, ctx, year: int) -> dict:
    """
    Spend analytics for `year`, honouring price history and each subscription's
    active window. Returns period_costs, yearly_total, per_sub, per_cat, months.
    """
    subs = get_all_subscriptions(db, ctx)
    periods_map = get_periods_map(db, [s["id"] for s in subs])
    per_sub, per_cat, per_freq, months, yearly_total = [], {}, {}, [0.0] * 12, 0.0

    for s in subs:
        periods = periods_map.get(s["id"], [])
        sub_year = year_cost(s, periods, year)
        if sub_year <= 0:
            continue
        per_sub.append((s["name"], sub_year))
        cat = category_label(s.get("category"))
        per_cat[cat] = round(per_cat.get(cat, 0.0) + sub_year, 2)
        flabel = frequency_label(s["frequency"] or "monthly",
                                 s.get("interval") or 1, s.get("base_unit"))
        per_freq[flabel] = round(per_freq.get(flabel, 0.0) + sub_year, 2)
        yearly_total += sub_year
        for i, m in enumerate(monthly_costs_for_year(s, periods, year)):
            months[i] += m

    yearly_total = round(yearly_total, 2)
    period_costs = {
        "daily":     round(yearly_total / 365.25, 2),
        "weekly":    round(yearly_total / 52.18,  2),
        "monthly":   round(yearly_total / 12,     2),
        "quarterly": round(yearly_total / 4,      2),
        "yearly":    yearly_total,
    }
    return {
        "period_costs": period_costs,
        "yearly_total": yearly_total,
        "per_sub":      per_sub,
        "per_cat":      list(per_cat.items()),
        "per_freq":     list(per_freq.items()),
        "months":       [round(m, 2) for m in months],
    }


@ar("/dashboard")
def get(req, session, year: int = None):
    ctx = req.scope["ctx"]
    if (r := require(ctx, "subscriptions.view")): return r
    db = get_db()

    current_year = timeutil.today().year
    year = year or current_year

    data = _year_analytics(db, ctx, year)

    cost_cards = Div(
        *[Div(
            Div(p.capitalize(), cls=COST_LABEL),
            Div(fmt_eur(data["period_costs"][p]), cls=COST_AMOUNT),
            cls=COST_CARD,
        ) for p in ["daily", "weekly", "monthly", "quarterly", "yearly"]],
        cls=COST_CARDS,
    )

    year_nav = Div(
        A("← Previous", href=f"/dashboard?year={year - 1}", role="button",
          cls=btn("outline", "sm")),
        Span(str(year), cls="text-sm font-semibold tabular-nums px-2"),
        A("Next →", href=f"/dashboard?year={year + 1}", role="button",
          cls=btn("outline", "sm")),
        cls="flex items-center gap-2 mb-4",
    )

    monthly_chart = section_card(
        heading=f"Monthly spend in {year}",
        *[bar_chart(MONTH_LABELS, data["months"])],
    )
    breakdown_charts = Div(
        section_card(
            heading=f"Spend by subscription ({year})",
            *[hbar_breakdown(data["per_sub"])],
        ),
        section_card(
            heading=f"Spend by category ({year})",
            *[hbar_breakdown(data["per_cat"])],
        ),
        section_card(
            heading=f"Spend by billing frequency ({year})",
            *[hbar_breakdown(data["per_freq"])],
        ),
        cls=CHARTS_GRID,
    )

    scope_label = ("All teams" if (ctx.view_all and ctx.is_super)
                   else (ctx.active_team_name or "No team"))
    return page_title("Dashboard"), nav_bar(ctx, "dashboard"), Main(
        Div(H2("Dashboard ", Small(f"· {scope_label}", cls="text-muted-foreground font-normal")),
            A("Manage subscriptions →", href="/manage", cls=LINK),
            cls=PAGE_HEADER),
        year_nav,
        cost_cards,
        monthly_chart,
        breakdown_charts,
    )
