"""
main.py — Application assembly.

Builds the single FastHTML `app`, registers every route module's APIRouter, and
ensures the schema exists. Importable as `app.main:app` (uvicorn) or via the
top-level `main.py` shim (`python main.py`).

Styling is native shadcn: Tailwind (Play CDN, v3) configured with shadcn's tokens,
plus shadcn's globals.css (tokens + @layer base) in app/styles.py. Components are
styled with shadcn utility class strings (see app/styles.py constants).
"""

from fasthtml.common import *

from app.config import SECRET_KEY, SECURE_COOKIES, SESSION_SAMESITE
from app.csrf import ASSET_SKIP, CSRF_JS, csrf_guard
from app.db import init_db
from app.routes import ALL_ROUTERS
from app.session import SKIP, load_ctx
from app.styles import GLOBALS

# Tailwind (Play CDN, v3) configured to consume shadcn's HSL tokens. Opacity
# modifiers (bg-primary/90, hover:bg-muted/50, …) work because the tokens are HSL.
TAILWIND_CONFIG = """
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        border: 'hsl(var(--border))', input: 'hsl(var(--input))', ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))', foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        success: 'hsl(var(--success))', warning: 'hsl(var(--warning))', info: 'hsl(var(--info))',
      },
      borderRadius: {
        lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
}
"""

# Applies the saved/preferred theme to <html> before render (no flash); toggle handler.
THEME_JS = """
(function () {
  try {
    var t = localStorage.getItem('theme');
    if (t === 'dark' || (t === null && window.matchMedia &&
        matchMedia('(prefers-color-scheme: dark)').matches))
      document.documentElement.classList.add('dark');
  } catch (e) {}
})();
function toggleTheme() {
  var dark = document.documentElement.classList.toggle('dark');
  try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch (e) {}
}
"""

# Drives the <details>-based shadcn DropdownMenu / Select:
#  • close on outside-click or Escape (one menu open at a time);
#  • when open, re-position the menu as position:fixed so it floats above any
#    clipping ancestor (e.g. a table wrapper with overflow);
#  • for select_menu, write the picked value + label into the hidden input.
DROPDOWN_JS = """
function closeDropdowns(except) {
  document.querySelectorAll('details[data-dropdown][open]').forEach(function (d) {
    if (d !== except) d.removeAttribute('open');
  });
}
function positionMenu(d) {
  var summary = d.querySelector(':scope > summary');
  var menu = d.querySelector(':scope > [role="menu"]');
  if (!summary || !menu) return;
  var r = summary.getBoundingClientRect();
  menu.style.position = 'fixed';
  menu.style.margin = '0';
  menu.style.right = 'auto';
  if (d.getAttribute('data-align') !== 'right') menu.style.minWidth = r.width + 'px';
  // Measure, then clamp inside the viewport (clientWidth/Height exclude scrollbars),
  // so the fixed menu never overflows and spawns a scrollbar — which would fire a
  // resize → reposition loop and make the scrollbar flicker.
  var mw = menu.offsetWidth, mh = menu.offsetHeight, gap = 4, pad = 8;
  var vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  var top = r.bottom + gap;
  if (top + mh > vh - pad) top = (r.top - gap - mh >= pad) ? r.top - gap - mh
                                                           : Math.max(pad, vh - pad - mh);
  var left = (d.getAttribute('data-align') === 'right') ? (r.right - mw) : r.left;
  left = Math.max(pad, Math.min(left, vw - pad - mw));
  menu.style.top = top + 'px';
  menu.style.left = left + 'px';
}
function repositionOpen() {
  document.querySelectorAll('details[data-dropdown][open]').forEach(positionMenu);
}
document.addEventListener('click', function (e) {
  var item = e.target.closest('details[data-select] [data-value]');
  if (item) {
    var d = item.closest('details[data-select]');
    var input = d.querySelector('input[type="hidden"]');
    var label = d.querySelector('[data-select-label]');
    if (input) { input.value = item.getAttribute('data-value');
                 input.dispatchEvent(new Event('change', { bubbles: true })); }
    if (label) label.textContent = item.textContent;
    d.querySelectorAll('[data-value]').forEach(function (b) {
      b.classList.remove('bg-accent', 'text-accent-foreground'); });
    item.classList.add('bg-accent', 'text-accent-foreground');
    d.removeAttribute('open');
    return;
  }
  closeDropdowns(e.target.closest('details[data-dropdown][open]'));
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') closeDropdowns(null);
});
document.addEventListener('toggle', function (e) {
  var d = e.target;
  if (d && d.matches && d.matches('details[data-dropdown]') && d.open) positionMenu(d);
}, true);
window.addEventListener('scroll', repositionOpen, true);
window.addEventListener('resize', repositionOpen);
"""

app, rt = fast_app(
    secret_key=SECRET_KEY,
    pico=False,
    hdrs=(
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Script(THEME_JS),
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(rel="stylesheet",
             href="https://fonts.googleapis.com/css2?family=Geist:wght@300..700"
                  "&family=Geist+Mono:wght@400..600&display=swap"),
        Script(src="https://cdn.tailwindcss.com"),
        Script(TAILWIND_CONFIG),
        Script(DROPDOWN_JS),
        CSRF_JS,
        Style(GLOBALS, type="text/tailwindcss"),
    ),
    # CSRF runs first (and on /login, /setup too); the auth gate runs second.
    before=(Beforeware(csrf_guard, skip=ASSET_SKIP), Beforeware(load_ctx, skip=SKIP)),
    same_site=SESSION_SAMESITE,
    sess_https_only=SECURE_COOKIES,
)

# Register all route modules onto the single app instance.
for _router in ALL_ROUTERS:
    _router.to_app(app)

# Ensure tables exist at startup (idempotent).
init_db()
