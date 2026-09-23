"""
dashboard.py — Spend dashboard: this-month billing, run-rate + summary stats,
cost cards, charts.

Three distinct lenses are surfaced:
  • Billing    — what is actually charged this calendar month vs the previous one,
    walking each subscription's real payment dates (what lands on the card).
  • Historical — what the selected calendar year actually cost: every payment
    charged in it, by real billing date and at the price of the period it falls in.
    The monthly bars therefore match the billing card for the same month.
  • Run-rate   — what is being paid right now: currently-active subscriptions at
    today's price, annualised. Answers "what's my ongoing commitment".
"""

import calendar
from datetime import date

from fasthtml.common import *

from app import timeutil
from app.authz import require
from app.components import (
    MONTH_LABELS,
    badge,
    bar_chart,
    category_label,
    disclosure,
    fmt_eur,
    hbar_breakdown,
    nav_bar,
    page_title,
    plural,
    section_card,
)
from app.cost_utils import (
    frequency_label,
    get_annual_cost,
    payments_between,
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
    MUTED_SM,
    PAGE_HEADER,
    btn,
)

ar = APIRouter()


def _year_analytics(subs: list, periods_map: dict, year: int) -> dict:
    """
    Spend analytics for `year` from the payments actually charged in it (price
    history and active windows included), plus current run-rate and a
    year-over-year comparison. `month_counts` counts payments per month.
    """
    today = timeutil.today_iso()
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    prev_start, prev_end = date(year - 1, 1, 1), date(year - 1, 12, 31)

    per_sub, per_cat, per_freq = [], {}, {}
    months, month_counts = [0.0] * 12, [0] * 12
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

        # The year total is the sum of this year's monthly payments, so it stays
        # consistent with the bars; the prior year feeds the YoY delta.
        prev_total += sum(pay["amount"] for pay in
                          payments_between(s, periods, prev_start, prev_end))
        sub_months, sub_counts = [0.0] * 12, [0] * 12
        for pay in payments_between(s, periods, year_start, year_end):
            sub_months[pay["date"].month - 1] += pay["amount"]
            sub_counts[pay["date"].month - 1] += 1
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
        for i in range(12):
            months[i] += sub_months[i]
            month_counts[i] += sub_counts[i]

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
        "month_counts":     month_counts,
        "run_rate_annual":  run_rate_annual,
        "run_rate_monthly": round(run_rate_annual / 12, 2),
        "active_count":     active_count,
        "total_count":      len(subs),
        "avg_per_sub":      round(yearly_total / len(per_sub), 2) if per_sub else 0.0,
        "top_sub":          max(per_sub, key=lambda t: t[1]) if per_sub else None,
    }


# ── This month vs last month (actual billing dates) ──────────────────────────

def _month_bounds(d: date) -> tuple:
    """(first, last) day of the calendar month containing `d`."""
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _previous_month(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def _month_label(d: date) -> str:
    return f"{calendar.month_name[d.month]} {d.year}"


def _charges_in_month(subs: list, periods_map: dict, any_day: date) -> list:
    """
    Every payment charged in the calendar month containing `any_day`, as
    [{date, amount, name}] sorted by date — real billing dates, not prorated cost.
    """
    start, end = _month_bounds(any_day)
    charges = []
    for s in subs:
        periods = periods_map.get(s["id"], [])
        for pay in payments_between(s, periods, start, end):
            charges.append({"date": pay["date"], "amount": pay["amount"], "name": s["name"]})
    charges.sort(key=lambda c: (c["date"], c["name"]))
    return charges


def _month_billing(subs: list, periods_map: dict, today: date) -> dict:
    """What lands on the card this month and what landed last month."""
    this_charges = _charges_in_month(subs, periods_map, today)
    prev_charges = _charges_in_month(subs, periods_map, _previous_month(today))
    remaining = [c for c in this_charges if c["date"] >= today]
    paid = [c for c in this_charges if c["date"] < today]

    this_total = round(sum(c["amount"] for c in this_charges), 2)
    prev_total = round(sum(c["amount"] for c in prev_charges), 2)
    return {
        "this_label":   _month_label(today),
        "prev_label":   _month_label(_previous_month(today)),
        "this_total":   this_total,
        "prev_total":   prev_total,
        "this_count":   len(this_charges),
        "prev_count":   len(prev_charges),
        "paid_total":   round(this_total - sum(c["amount"] for c in remaining), 2),
        "remaining":    remaining,
        "paid":         paid,
        "remaining_total": round(sum(c["amount"] for c in remaining), 2),
        "delta":        round(this_total - prev_total, 2),
    }


def _stat(label, value, caption=None):
    return Div(
        Div(label, cls=COST_LABEL),
        Div(value, cls=COST_AMOUNT),
        Div(caption, cls="text-xs text-muted-foreground mt-1 truncate") if caption else "",
        cls=COST_CARD,
    )


def _charge_row(c: dict, today: date, billed: bool = False):
    when = ("today" if c["date"] == today
            else (f"in {(c['date'] - today).days}d" if c["date"] > today else "billed"))
    return Div(
        Span(f"{c['date'].day} {calendar.month_abbr[c['date'].month]}",
             cls="w-14 shrink-0 text-muted-foreground tabular-nums"),
        Span(c["name"], cls="flex-1 truncate"),
        Span(when, cls="text-xs text-muted-foreground mr-3"),
        Strong(fmt_eur(c["amount"]), cls="tabular-nums"),
        cls="flex items-center gap-2 py-1.5 border-b last:border-0 text-sm"
            + (" text-muted-foreground" if billed else ""),
    )


def _month_card(b: dict, today: date):
    """This month vs last month, by actual billing date, plus what is still due."""
    delta, prev_total = b["delta"], b["prev_total"]
    if prev_total > 0:
        pct = delta / prev_total * 100
        change_badge = badge(f"{'▲' if delta >= 0 else '▼'} {abs(pct):.0f}%",
                             "warning" if delta >= 0 else "success")
    else:
        change_badge = badge("no charges last month", "info")

    change_tile = Div(
        Div("vs last month", cls=COST_LABEL),
        Div(f"{'+' if delta >= 0 else '−'}{fmt_eur(abs(delta))}", cls=COST_AMOUNT),
        Div(change_badge, cls="mt-1"),
        cls=COST_CARD,
    )

    if b["remaining"]:
        shown = b["remaining"][:6]
        rows = [_charge_row(c, today) for c in shown]
        if len(b["remaining"]) > len(shown):
            rows.append(P(f"+ {plural(len(b['remaining']) - len(shown), 'more payment')} "
                          f"this month", cls=MUTED_SM + " pt-2"))
        still_due = Div(
            Div(Span("Still to pay this month", cls="text-sm font-medium"),
                Strong(fmt_eur(b["remaining_total"]), cls="tabular-nums"),
                cls="flex items-center justify-between mb-1"),
            *rows,
        )
    else:
        still_due = P("No payments are scheduled this month." if b["this_count"] == 0 else
                      "Nothing left to pay this month — every charge has already been billed.",
                      cls=MUTED_SM)

    already_billed = (
        disclosure(f"{plural(len(b['paid']), 'payment')} already billed · "
                   f"{fmt_eur(b['paid_total'])}",
                   *[_charge_row(c, today, billed=True) for c in b["paid"]])
        if b["paid"] else ""
    )

    return section_card(
        Div(
            _stat(f"This month · {b['this_label']}", fmt_eur(b["this_total"]),
                  plural(b["this_count"], "payment")),
            _stat(f"Last month · {b['prev_label']}", fmt_eur(b["prev_total"]),
                  plural(b["prev_count"], "payment")),
            change_tile,
            cls="grid gap-4 sm:grid-cols-3 mb-4",
        ),
        still_due,
        Div(already_billed, cls="mt-3 pt-3 border-t") if already_billed else "",
        heading="What you pay this month",
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

    today = timeutil.today()
    year = year or today.year

    subs = get_all_subscriptions(db, ctx)
    periods_map = get_periods_map(db, [s["id"] for s in subs])
    data = _year_analytics(subs, periods_map, year)
    billing = _month_billing(subs, periods_map, today)

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
        cls="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6",
    )
    year_cards = Div(
        _stat("Avg / subscription", fmt_eur(data["avg_per_sub"]), f"across {year}"),
        _stat("Most expensive", fmt_eur(top[1]) if top else "—", top[0] if top else None),
        cls="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5",
    )

    cost_cards = Div(
        *[Div(
            Div(p.capitalize(), cls=COST_LABEL),
            Div(fmt_eur(data["period_costs"][p]), cls=COST_AMOUNT),
            cls=COST_CARD,
        ) for p in ["daily", "weekly", "monthly", "quarterly", "yearly"]],
        cls=COST_CARDS,
    )

    monthly_chart = section_card(
        heading=f"Monthly spend in {year}",
        *[bar_chart(MONTH_LABELS, data["months"],
                    tip_labels=[f"{calendar.month_name[m + 1]} {year}" for m in range(12)],
                    notes=[plural(c, "payment") for c in data["month_counts"]]),
          P("Hover a bar for the exact amount — click to keep it open.", cls=MUTED_SM)],
    )

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
        P("Right now", cls="text-sm font-medium text-muted-foreground mb-2"),
        _month_card(billing, today),
        run_rate_cards,
        P("Calendar year", cls="text-sm font-medium text-muted-foreground mb-2"),
        year_nav,
        total_banner,
        year_cards,
        P(f"Average per period ({year})", cls="text-sm font-medium text-muted-foreground mb-2"),
        cost_cards,
        monthly_chart,
        breakdown_charts,
    )
