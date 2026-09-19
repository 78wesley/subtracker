"""
charts.py — Inline SVG / CSS charts, styled with shadcn token utilities
(fill-primary / stroke-border / fill-muted-foreground).

Every data mark (bar, point, breakdown row) carries `data-tip-*` attributes and is
keyboard-focusable; CHART_JS (app/main.py) turns those into a hover tooltip that
can be pinned by clicking/tapping the mark. Marks are wrapped in a <g> together
with a transparent full-height hit area, so the whole column is hoverable — not
just the painted bar.
"""

from fasthtml.common import *
from fasthtml.svg import Circle, G, Line, Polygon, Polyline, Rect, Svg, Text

# Shared SVG viewBox geometry for line_chart / bar_chart. The charts scale to their
# container via `w-full` + viewBox; these are the internal coordinate units only.
# Rendered height = container width × (height / _CHART_W), so `height` is really an
# aspect ratio: the flatter it is, the shorter the chart.
_CHART_W = 640                              # viewBox width
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 46, 10, 10, 24  # plot insets (left axis labels, etc.)
_HEIGHT = 150                               # default viewBox height (compact)
_GRID_LINES = 4                             # horizontal gridlines (incl. baseline)

_AXIS_TEXT = "fill-muted-foreground text-[11px]"


def _tip(label: str, value: str, note: str | None = None) -> dict:
    """Attributes that make an element a tooltip target for CHART_JS."""
    aria = f"{label}: {value}" + (f", {note}" if note else "")
    attrs = {"data-tip-label": label, "data-tip-value": value,
             "tabindex": "0", "role": "button", "aria-label": aria}
    if note:
        attrs["data-tip-note"] = note
    return attrs


def _gridlines(vmax, pad_l, pad_t, plot_h, right_x, fmt) -> list:
    """Horizontal gridlines with value labels, bottom (0) to top (vmax)."""
    out = []
    for i in range(_GRID_LINES + 1):
        frac = i / _GRID_LINES
        y = pad_t + plot_h * (1 - frac)
        out.append(Line(x1=pad_l, y1=y, x2=right_x, y2=y,
                        cls="stroke-border" if i else "stroke-border/80"))
        out.append(Text(fmt(vmax * frac), x=pad_l - 6, y=y + 3,
                        text_anchor="end", cls=_AXIS_TEXT))
    return out


def _at(seq, i, default=None):
    """seq[i] when the optional per-mark list is supplied and long enough."""
    return seq[i] if seq and i < len(seq) else default


def line_chart(labels: list, values: list, *, height: int = _HEIGHT,
               fmt=lambda v: f"€{v:,.0f}", tip_fmt=None, notes: list = None,
               tip_labels: list = None) -> object:
    """Responsive line chart (with soft area fill) rendered as inline SVG.

    Suited to cumulative / running-total series where the trend matters more
    than per-bucket magnitude."""
    if not values or max(values) <= 0:
        return P("No data for this period.", cls="text-muted-foreground text-center py-8")

    tip_fmt = tip_fmt or (lambda v: f"€{v:,.2f}")
    n = len(values)
    W, H = _CHART_W, height
    pad_l, pad_r, pad_t, pad_b = _PAD_L, _PAD_R, _PAD_T, _PAD_B
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    vmax = max(values)
    base_y = pad_t + plot_h

    xs = [pad_l + (plot_w * i / (n - 1) if n > 1 else plot_w / 2) for i in range(n)]
    ys = [pad_t + plot_h * (1 - (v / vmax if vmax else 0)) for v in values]

    elems = _gridlines(vmax, pad_l, pad_t, plot_h, W - pad_r, fmt)

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    elems.append(Polygon(points=f"{xs[0]:.1f},{base_y:.1f} {pts} {xs[-1]:.1f},{base_y:.1f}",
                         cls="fill-primary/10"))
    elems.append(Polyline(points=pts, cls="fill-none stroke-primary", stroke_width="2"))
    for i, ((x, y), (lab, val)) in enumerate(zip(zip(xs, ys), zip(labels, values))):
        elems.append(G(
            Circle(cx=x, cy=y, r=3.5, cls="fill-primary chart-mark"),
            Rect(x=x - plot_w / (2 * n), y=pad_t, width=plot_w / n, height=plot_h,
                 fill="transparent"),
            Text(lab, x=x, y=H - pad_b + 15, text_anchor="middle", cls=_AXIS_TEXT),
            cls="group cursor-pointer chart-hit",
            **_tip(_at(tip_labels, i, lab), tip_fmt(val), _at(notes, i)),
        ))

    return Svg(*elems, viewBox=f"0 0 {W} {H}", cls="w-full h-auto",
               preserveAspectRatio="xMidYMid meet", role="img")


def bar_chart(labels: list, values: list, *, height: int = _HEIGHT,
              fmt=lambda v: f"€{v:,.0f}", tip_fmt=None, notes: list = None,
              tip_labels: list = None) -> object:
    """Responsive vertical bar chart rendered as inline SVG.

    `tip_labels` optionally replaces the (abbreviated) axis label inside the tooltip,
    and `notes` supplies a third tooltip line per bar (e.g. "3 subscriptions").
    """
    if not values or max(values) <= 0:
        return P("No data for this period.", cls="text-muted-foreground text-center py-8")

    tip_fmt = tip_fmt or (lambda v: f"€{v:,.2f}")
    n = len(values)
    W, H = _CHART_W, height
    pad_l, pad_r, pad_t, pad_b = _PAD_L, _PAD_R, _PAD_T, _PAD_B
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    vmax = max(values)
    slot = plot_w / n
    bar_w = slot * 0.62

    elems = _gridlines(vmax, pad_l, pad_t, plot_h, W - pad_r, fmt)

    for i, (lab, val) in enumerate(zip(labels, values)):
        bh = (val / vmax) * plot_h if vmax else 0
        x = pad_l + slot * i + (slot - bar_w) / 2
        y = pad_t + (plot_h - bh)
        elems.append(G(
            # The painted bar, then a transparent full-height hit area so the whole
            # column (including empty space above a short bar) is hoverable.
            Rect(x=x, y=y, width=bar_w, height=bh, rx=3,
                 cls="fill-primary transition-[fill] group-hover:fill-primary/75 chart-mark"),
            Rect(x=pad_l + slot * i, y=pad_t, width=slot, height=plot_h, fill="transparent"),
            Text(lab, x=x + bar_w / 2, y=H - pad_b + 15,
                 text_anchor="middle", cls=_AXIS_TEXT),
            cls="group cursor-pointer chart-hit",
            **_tip(_at(tip_labels, i, lab), tip_fmt(val), _at(notes, i)),
        ))

    return Svg(*elems, viewBox=f"0 0 {W} {H}", cls="w-full h-auto",
               preserveAspectRatio="xMidYMid meet", role="img")


def hbar_breakdown(items: list, *, fmt=lambda v: f"€{v:,.2f}", note_fmt=None) -> object:
    """Horizontal bar breakdown from [(label, value)], sorted desc by value.

    Each row is a tooltip target showing its value and share of the total (or
    `note_fmt(value, total)` when supplied)."""
    items = [(lab, v) for lab, v in items if v > 0]
    if not items:
        return P("No active subscriptions in this year.",
                 cls="text-muted-foreground text-center py-8")
    items.sort(key=lambda t: t[1], reverse=True)
    vmax = items[0][1]
    total = sum(v for _, v in items)
    note_fmt = note_fmt or (
        lambda v, t: f"{v / t * 100:.1f}% of {fmt(t)} total" if t else "")
    rows = []
    for lab, val in items:
        pct = (val / vmax) * 100 if vmax else 0
        rows.append(Div(
            Span(lab, cls="break-words leading-snug"),
            Div(Div(cls="bg-primary h-full rounded-full transition-[width]",
                    style=f"width:{pct:.1f}%"),
                cls="bg-muted rounded-full h-2 overflow-hidden"),
            Span(fmt(val), cls="text-right text-muted-foreground tabular-nums"),
            cls="chart-hit grid grid-cols-[6.5rem_1fr_4.5rem] sm:grid-cols-[11rem_1fr_5.5rem] "
                "items-center gap-2 mb-1 py-1 px-1.5 -mx-1.5 rounded-md text-sm "
                "cursor-pointer transition-colors hover:bg-muted/60",
            **_tip(lab, fmt(val), note_fmt(val, total)),
        ))
    return Div(*rows)
