"""
dashboard.py — Spend dashboard: run-rate + summary stats, cost cards, charts.

Two distinct lenses are surfaced:
  • Historical — what the selected calendar year actually cost, prorating each
    subscription over the days it was active (period + price aware).
  • Run-rate  — what is being paid right now: currently-active subscriptions at
    today's price, annualised. Answers "what's my ongoing commitment".
"""

from fasthtml.common import *

from app import timeutil
from app.authz import require
from app.components import (
    MONTH_LABELS,
    badge,
    bar_chart,
    category_label,
    fmt_eur,
    hbar_breakdown,
    nav_bar,
    page_title,
    section_card,
)
from app.cost_utils import (
    frequency_label,
    get_annual_cost,
    monthly_costs_for_year,
    year_cost,
)
from app.db import (
    current_price,
    get_all_subscriptions,
    get_db,
    get_periods_map,
    is_active_on,
)
from app.permissions import Perm
from app.styles import (
    CHARTS_GRID,
    COST_AMOUNT,
    COST_CARD,
    COST_CARDS,
    COST_LABEL,
    LINK,
    PAGE_HEADER,
    btn,
)

ar = APIRouter()


def _year_analytics(db, ctx, year: int) -> dict:
    """
    Spend analytics for `year`, honouring price history and each subscription's
    active windows, plus current run-rate and a year-over-year comparison.
    """
    subs = get_all_subscriptions(db, ctx)
    periods_map = get_periods_map(db, [s["id"] for s in subs])
    today = timeutil.today_iso()

    per_sub, per_cat, per_freq, months = [], {}, {}, [0.0] * 12
    yearly_total, prev_total = 0.0, 0.0
    run_rate_annual, active_count = 0.0, 0

    for s in subs:
        periods = periods_map.get(s["id"], [])

        # Run-rate: only subscriptions active *today*, at today's price.
        if is_active_on(periods, today):
            active_count += 1
            price = current_price(periods, today)
            if price is not None:
                run_rate_annual += get_annual_cost(
                    price, s["frequency"], s.get("interval") or 1, s.get("base_unit"))

        # One pass over each subscription's periods yields both the prior-year total
        # (for the YoY delta) and this year's 12 monthly costs; the year total is just
        # their sum, so it stays consistent with the bars and needs no extra walk.
        prev_total += year_cost(s, periods, year - 1)
        sub_months = monthly_costs_for_year(s, periods, year)
        sub_year = round(sum(sub_months), 2)
        if sub_year <= 0:
            continue
        per_sub.append((s["name"], sub_year))
        cat = category_label(s.get("category"))
        per_cat[cat] = round(per_cat.get(cat, 0.0) + sub_year, 2)
        flabel = frequency_label(s["frequency"] or "monthly",
                                 s.get("interval") or 1, s.get("base_unit"))
        per_freq[flabel] = round(per_freq.get(flabel, 0.0) + sub_year, 2)
        yearly_total += sub_year
        for i, m in enumerate(sub_months):
            months[i] += m

    prev_total = round(prev_total, 2)
    yearly_total = round(yearly_total, 2)
    months = [round(m, 2) for m in months]
    run_rate_annual = round(run_rate_annual, 2)

    period_costs = {
        "daily":     round(yearly_total / 365.25, 2),
        "weekly":    round(yearly_total / 52.18,  2),
        "monthly":   round(yearly_total / 12,     2),
        "quarterly": round(yearly_total / 4,      2),
        "yearly":    yearly_total,
    }
    return {
        "period_costs":     period_costs,
        "yearly_total":     yearly_total,
        "prev_total":       prev_total,
        "per_sub":          per_sub,
        "per_cat":          list(per_cat.items()),
        "per_freq":         list(per_freq.items()),
        "months":           months,
        "run_rate_annual":  run_rate_annual,
        "run_rate_monthly": round(run_rate_annual / 12, 2),
        "active_count":     active_count,
        "total_count":      len(subs),
        "avg_per_sub":      round(yearly_total / len(per_sub), 2) if per_sub else 0.0,
        "top_sub":          max(per_sub, key=lambda t: t[1]) if per_sub else None,
    }


def _stat(label, value, caption=None):
    return Div(
        Div(label, cls=COST_LABEL),
        Div(value, cls=COST_AMOUNT),
        Div(caption, cls="text-xs text-muted-foreground mt-1 truncate") if caption else "",
        cls=COST_CARD,
    )


def _yoy_badge(cur: float, prev: float, prev_year: int):
    """A coloured delta badge: spending less than last year is 'good' (success)."""
    if prev <= 0:
        return badge(f"no {prev_year} data", "info")
    pct = (cur - prev) / prev * 100
    arrow = "▲" if pct >= 0 else "▼"
    kind = "warning" if pct >= 0 else "success"
    return badge(f"{arrow} {abs(pct):.0f}% vs {prev_year}", kind)


@ar("/dashboard")
def get(req, session, year: int = None):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_VIEW)): return r
    db = get_db()

    current_year = timeutil.today().year
    year = year or current_year

    data = _year_analytics(db, ctx, year)

    year_nav = Div(
        A("← Previous", href=f"/dashboard?year={year - 1}", role="button",
          cls=btn("outline", "sm")),
        Span(str(year), cls="text-sm font-semibold tabular-nums px-2"),
        A("Next →", href=f"/dashboard?year={year + 1}", role="button",
          cls=btn("outline", "sm")),
        cls="flex items-center gap-2 mb-4",
    )

    # Headline: the year's total spend with a year-over-year delta.
    total_banner = Div(
        Div(
            Span(f"Total spend {year}", cls="text-sm text-muted-foreground"),
            Div(fmt_eur(data["yearly_total"]), cls="text-3xl font-bold tracking-tight"),
        ),
        Div(_yoy_badge(data["yearly_total"], data["prev_total"], year - 1),
            Div(f"{year - 1}: {fmt_eur(data['prev_total'])}",
                cls="text-xs text-muted-foreground mt-1 text-right")),
        cls="flex items-end justify-between rounded-xl border bg-card p-5 mb-5",
    )

    top = data["top_sub"]
    run_rate_cards = Div(
        _stat("Monthly run-rate", fmt_eur(data["run_rate_monthly"]),
              "active subs · today's prices"),
        _stat("Projected annual", fmt_eur(data["run_rate_annual"]),
              "if nothing changes"),
        _stat("Active subscriptions", str(data["active_count"]),
              f"of {data['total_count']} total"),
        _stat("Avg / subscription", fmt_eur(data["avg_per_sub"]), f"across {year}"),
        _stat("Most expensive", fmt_eur(top[1]) if top else "—", top[0] if top else None),
        cls=COST_CARDS,
    )

    cost_cards = Div(
        *[Div(
            Div(p.capitalize(), cls=COST_LABEL),
            Div(fmt_eur(data["period_costs"][p]), cls=COST_AMOUNT),
            cls=COST_CARD,
        ) for p in ["daily", "weekly", "monthly", "quarterly", "yearly"]],
        cls=COST_CARDS,
    )

    monthly_chart = section_card(heading=f"Monthly spend in {year}",
                                 *[bar_chart(MONTH_LABELS, data["months"])])

    breakdown_charts = Div(
        section_card(heading=f"Spend by subscription ({year})",
                     *[hbar_breakdown(data["per_sub"])]),
        section_card(heading=f"Spend by category ({year})",
                     *[hbar_breakdown(data["per_cat"])]),
        section_card(heading=f"Spend by billing frequency ({year})",
                     *[hbar_breakdown(data["per_freq"])]),
        cls=CHARTS_GRID,
    )

    scope_label = ("All teams" if (ctx.view_all and ctx.is_super)
                   else (ctx.active_team_name or "No team"))
    return page_title("Dashboard"), nav_bar(ctx, "dashboard"), Main(
        Div(H2("Dashboard ", Small(f"· {scope_label}", cls="text-muted-foreground font-normal")),
            A("Manage subscriptions →", href="/manage", cls=LINK),
            cls=PAGE_HEADER),
        year_nav,
        total_banner,
        P("Right now", cls="text-sm font-medium text-muted-foreground mb-2"),
        run_rate_cards,
        P(f"Average per period ({year})", cls="text-sm font-medium text-muted-foreground mb-2"),
        cost_cards,
        monthly_chart,
        breakdown_charts,
    )
