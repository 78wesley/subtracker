"""
styles.py — shadcn/ui for SubTracker, the "native" way.

There is no bespoke component CSS. The only stylesheet is shadcn's `globals.css`
(design tokens + the small @layer base), processed by the Tailwind Play CDN. Every
component is styled with shadcn's real Tailwind utility class strings, exposed here
as constants/helpers and applied via `cls=` on the markup.

Tokens are HSL (shadcn's Tailwind-v3 default "neutral" palette — same grayscale as
ui.shadcn.com) so opacity modifiers like `bg-primary/90` work natively on the v3 CDN.
"""

# shadcn globals.css — tokens + base layer only (no component styling).
GLOBALS = """
:root {
  --background: 0 0% 100%;
  --foreground: 0 0% 3.9%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 3.9%;
  --popover: 0 0% 100%;
  --popover-foreground: 0 0% 3.9%;
  --primary: 0 0% 9%;
  --primary-foreground: 0 0% 98%;
  --secondary: 0 0% 96.1%;
  --secondary-foreground: 0 0% 9%;
  --muted: 0 0% 96.1%;
  --muted-foreground: 0 0% 45.1%;
  --accent: 0 0% 96.1%;
  --accent-foreground: 0 0% 9%;
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 0 0% 98%;
  --border: 0 0% 89.8%;
  --input: 0 0% 89.8%;
  --ring: 0 0% 3.9%;
  --success: 142 71% 45%;
  --warning: 38 92% 50%;
  --info: 217 91% 60%;
  --radius: 0.5rem;
  color-scheme: light;
}
.dark {
  --background: 0 0% 3.9%;
  --foreground: 0 0% 98%;
  --card: 0 0% 3.9%;
  --card-foreground: 0 0% 98%;
  --popover: 0 0% 3.9%;
  --popover-foreground: 0 0% 98%;
  --primary: 0 0% 98%;
  --primary-foreground: 0 0% 9%;
  --secondary: 0 0% 14.9%;
  --secondary-foreground: 0 0% 98%;
  --muted: 0 0% 14.9%;
  --muted-foreground: 0 0% 63.9%;
  --accent: 0 0% 14.9%;
  --accent-foreground: 0 0% 98%;
  --destructive: 0 62.8% 30.6%;
  --destructive-foreground: 0 0% 98%;
  --border: 0 0% 14.9%;
  --input: 0 0% 14.9%;
  --ring: 0 0% 83.1%;
  --success: 142 71% 45%;
  --warning: 38 92% 50%;
  --info: 217 91% 60%;
  color-scheme: dark;
}
@layer base {
  * { @apply border-border; }
  body { @apply bg-background text-foreground font-sans antialiased mx-auto max-w-[1280px] px-4 py-5 sm:px-6 sm:py-6; }
  h1 { @apply text-2xl font-semibold tracking-tight; }
  h2 { @apply text-xl font-semibold tracking-tight; }
  h3 { @apply text-base font-semibold; }
  a { @apply text-foreground hover:text-primary; }
  /* Theme-toggle icon swap (only non-component CSS that has no utility equivalent) */
  .theme-icon-dark { display: none; }
  .dark .theme-icon-dark { display: inline; }
  .dark .theme-icon-light { display: none; }
}

/* Chart marks (app/components/charts.py + CHART_JS): keyboard focus ring, and the
   highlighted state of the mark whose tooltip is pinned. */
.chart-hit:focus { outline: none; }
.chart-hit:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
  border-radius: 4px;
}
svg .chart-hit.chart-pinned .chart-mark {
  fill: hsl(var(--primary) / 0.75);
  stroke: hsl(var(--ring));
  stroke-width: 1.5;
}
div.chart-hit.chart-pinned { background-color: hsl(var(--muted)); }

/* Disclosure toggle (app/components/widgets.py): flip the chevron when open. */
details[data-disclosure][open] > summary svg { transform: rotate(180deg); }

/* shadcn DropdownMenu (built on <details>): open animation + trigger chevron flip. */
details[data-dropdown][open] > summary svg { transform: rotate(180deg); }
details[data-dropdown] > [role="menu"] { animation: dropdown-in 0.12s ease-out; }
@keyframes dropdown-in {
  from { opacity: 0; transform: translateY(-4px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0)    scale(1); }
}
"""

# ── shadcn component class strings (the real recipes) ─────────────────────────

_BTN_BASE = ("inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md "
             "text-sm font-medium transition-colors focus-visible:outline-none "
             "focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none "
             "disabled:opacity-50")
_BTN_VARIANT = {
    "default":     "bg-primary text-primary-foreground shadow hover:bg-primary/90",
    "secondary":   "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
    "outline":     "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
    "destructive": "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
    "ghost":       "hover:bg-accent hover:text-accent-foreground",
}
_BTN_SIZE = {
    "default": "h-9 px-4 py-2",
    "sm":      "h-8 rounded-md px-3 text-xs",
    "lg":      "h-10 rounded-md px-8",
    "icon":    "h-9 w-9",
}


def btn(variant: str = "default", size: str = "default", extra: str = "") -> str:
    """Compose a shadcn Button class string."""
    return " ".join(filter(None, [_BTN_BASE, _BTN_VARIANT.get(variant, _BTN_VARIANT["default"]),
                                   _BTN_SIZE.get(size, _BTN_SIZE["default"]), extra]))


INPUT = ("flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm "
         "shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none "
         "focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50")
# Fixed-width form control (no w-full) for inline filter bars.
CONTROL = ("h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm "
           "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring")
TEXTAREA = ("flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 "
            "text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none "
            "focus-visible:ring-1 focus-visible:ring-ring")
LABEL = "text-sm font-medium leading-none"

CARD = "rounded-xl border bg-card text-card-foreground shadow"
SECTION = CARD + " p-6 mb-5"          # section-card
COST_CARD = CARD + " p-5 text-center"

_BADGE_BASE = "inline-flex items-center gap-1 rounded-md border px-2.5 py-0.5 text-xs font-semibold"
_BADGE_VARIANT = {
    "default":   "border-transparent bg-primary text-primary-foreground",
    "secondary": "border-transparent bg-secondary text-secondary-foreground",
    "role":      "border-transparent bg-secondary text-secondary-foreground",
    "outline":   "text-foreground",
    "active":    "border-transparent bg-success/15 text-success",
    "success":   "border-transparent bg-success/15 text-success",
    "inactive":  "border-transparent bg-destructive/10 text-destructive",
    "warn":      "border-transparent bg-warning/15 text-warning",
    "warning":   "border-transparent bg-warning/15 text-warning",
    "info":      "border-transparent bg-info/15 text-info",
}


def badge_cls(kind: str = "default") -> str:
    return f"{_BADGE_BASE} {_BADGE_VARIANT.get(kind, _BADGE_VARIANT['default'])}"


# One class on <table> styles all child th/td/tr via Tailwind arbitrary variants.
TABLE = ("w-full caption-bottom text-sm "
         "[&_thead_tr]:border-b [&_th]:h-10 [&_th]:px-2 [&_th]:text-left [&_th]:align-middle "
         "[&_th]:font-medium [&_th]:text-muted-foreground "
         "[&_tbody_tr]:border-b [&_tbody_tr]:transition-colors [&_tbody_tr:hover]:bg-muted/50 "
         "[&_td]:p-2 [&_td]:align-middle [&_tbody_tr:last-child]:border-0")
TABLE_WRAP = "relative w-full overflow-x-auto"

# Layout helpers
PAGE = "mx-auto max-w-[1280px] p-6"
PAGE_HEADER = "flex items-center justify-between gap-4 flex-wrap mb-5"
NAV = (CARD + " flex items-center flex-wrap gap-x-4 gap-y-2 px-3 py-2.5 mb-5 sm:gap-x-5 sm:px-4 sm:mb-6")
NAV_LINK = "text-sm text-muted-foreground hover:text-foreground transition-colors"
NAV_LINK_ACTIVE = "text-sm text-foreground font-medium"
FILTERS = "flex flex-wrap items-end gap-4 mb-4"
FIELD = "grid gap-1.5"      # label + control
ALERT = {
    "warning": "rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm mb-4",
    "error":   "rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive mb-4",
    "success": "rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm mb-4",
}
MUTED = "text-muted-foreground"
MUTED_SM = "text-sm text-muted-foreground"
LINK = "text-sm text-muted-foreground hover:text-foreground transition-colors"
COST_CARDS = "grid grid-cols-2 md:grid-cols-5 gap-4 mb-5"
COST_LABEL = "text-xs uppercase tracking-wide text-muted-foreground mb-1.5"
COST_AMOUNT = "text-2xl font-semibold tracking-tight"
CHARTS_GRID = "grid md:grid-cols-2 gap-5 mb-5"
ROW2 = "grid gap-4 sm:grid-cols-2"        # two-column form row
INLINE_FORM = "flex items-center gap-2 m-0"  # role/membership inline set forms
CONTENT = "grid gap-5"                     # page main wrapper
