"""
fmt.py — Small formatting helpers (no FastHTML dependency).
"""

import json

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_eur(amount: float) -> str:
    return f"€{amount:,.2f}"


def plural(n: int, noun: str) -> str:
    """'1 payment' / '3 payments' — naive -s plural, fine for the nouns we use."""
    return f"{n} {noun}{'' if n == 1 else 's'}"


def category_label(cat) -> str:
    """Display name for a category, defaulting empty/None to 'Uncategorized'."""
    return (cat or "").strip() or "Uncategorized"


def truncate(text: str, n: int = 45) -> str:
    t = text or ""
    return t[:n] + "…" if len(t) > n else t


def json_pretty(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2) if raw else ""
    except Exception:
        return raw or ""
