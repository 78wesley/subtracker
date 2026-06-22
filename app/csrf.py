"""
csrf.py — Cross-site request forgery protection.

Strategy (synchroniser-token, scoped to the signed session):
  * a per-session random token is minted on first render and stored in the
    (signed, HttpOnly) session cookie via `ensure_token`;
  * every rendered page exposes it in a <meta name="csrf-token"> tag (see
    `csrf_meta`, emitted by the nav bar and the login/setup pages);
  * client JS (CSRF_JS, injected globally in app.main) copies that token into a
    hidden `csrf_token` field on every POST form submit and into the
    `X-CSRFToken` header on every HTMX request — so no individual form or button
    needs to know about CSRF;
  * `csrf_guard` (a Beforeware running ahead of the auth gate) rejects any unsafe
    request whose submitted token does not match the session token.

Because the token lives in the signed session cookie, an attacker on another
origin can neither read it nor forge a request carrying the matching value.
"""

import secrets

from fasthtml.common import Meta, Response, Script

SESSION_KEY = "_csrf"
FIELD_NAME = "csrf_token"
HEADER_NAME = "x-csrftoken"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Static-asset paths the CSRF gate never needs to run on. Unlike the auth gate it
# deliberately does NOT skip /login or /setup: those POSTs must be protected too.
ASSET_SKIP = [r"/[^/]*\.(css|js|ico|png|jpe?g|svg|woff2?|map|txt)", r"/favicon\.ico"]


def ensure_token(session: dict) -> str:
    """Return the session's CSRF token, minting and storing one if absent."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_KEY] = token
    return token


def csrf_meta(session: dict) -> Meta:
    """<meta> tag carrying the session CSRF token for the client JS to read."""
    return Meta(name="csrf-token", content=ensure_token(session))


async def csrf_guard(req, session):
    """
    Beforeware: reject unsafe requests lacking a valid CSRF token.

    Returns a 403 Response on failure (which short-circuits the request) or None
    to let the request proceed.
    """
    if req.method in SAFE_METHODS:
        return None
    expected = session.get(SESSION_KEY)
    sent = req.headers.get(HEADER_NAME)
    if not sent:
        # Form was already parsed (and cached) by FastHTML before this runs.
        form = await req.form()
        sent = form.get(FIELD_NAME)
    if not (expected and sent and secrets.compare_digest(str(sent), str(expected))):
        return Response("CSRF validation failed. Reload the page and try again.",
                        status_code=403)
    return None


# Injected into every page (app.main hdrs). Auto-attaches the token to native POST
# form submits and to HTMX requests, reading it from the <meta> tag, so handlers
# and templates stay CSRF-unaware.
CSRF_JS = Script("""
(function () {
  function token() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : null;
  }
  // Native form POSTs: inject a hidden field just before submission.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.matches || !form.matches('form')) return;
    if ((form.getAttribute('method') || 'get').toLowerCase() !== 'post') return;
    if (form.querySelector('input[name="csrf_token"]')) return;
    var t = token();
    if (!t) return;
    var i = document.createElement('input');
    i.type = 'hidden'; i.name = 'csrf_token'; i.value = t;
    form.appendChild(i);
  }, true);
  // HTMX requests: add the header for every non-GET issued by hx-* attributes.
  document.addEventListener('htmx:configRequest', function (e) {
    var t = token();
    if (t) e.detail.headers['X-CSRFToken'] = t;
  });
})();
""")
