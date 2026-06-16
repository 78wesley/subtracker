"""
main.py — Application assembly.

Builds the single FastHTML `app`, registers every route module's APIRouter, and
ensures the schema exists. Importable as `app.main:app` (uvicorn) or via the
top-level `main.py` shim (`python main.py`).
"""

from fasthtml.common import *

from app.config import SECRET_KEY
from app.styles import CSS
from app.db import init_db
from app.routes import ALL_ROUTERS
from app.session import load_ctx, SKIP

# Tailwind (Play CDN) configured with the shadcn design tokens. Preflight is off so
# it never clobbers the base element styling defined in styles.py (which also makes
# the page look correct before/independently of the CDN finishing).
TAILWIND_CONFIG = """
tailwind.config = {
  darkMode: 'class',
  corePlugins: { preflight: false },
  theme: { extend: {
    colors: {
      border: 'hsl(var(--border))', input: 'hsl(var(--input))', ring: 'hsl(var(--ring))',
      background: 'hsl(var(--background))', foreground: 'hsl(var(--foreground))',
      primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
      secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
      destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
      muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
      accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
      card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
    },
    borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)' },
  } }
}
"""

# Applies the saved/preferred theme to <html> before the body renders (no flash),
# and defines the nav toggle handler. shadcn dark mode = a `.dark` class on <html>.
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

app, rt = fast_app(
    secret_key=SECRET_KEY,
    pico=False,
    hdrs=(
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Script(THEME_JS),
        Script(src="https://cdn.tailwindcss.com"),
        Script(TAILWIND_CONFIG),
        Style(CSS),
    ),
    before=Beforeware(load_ctx, skip=SKIP),
)

# Register all route modules onto the single app instance.
for _router in ALL_ROUTERS:
    _router.to_app(app)

# Ensure tables exist at startup (idempotent).
init_db()
