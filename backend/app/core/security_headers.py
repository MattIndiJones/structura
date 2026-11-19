"""Browser security headers on every response (P1-8, finding S1).

Nothing set them before: no content policy, no framing ban, no HSTS. The
policy follows what the interface actually loads:

- scripts and styles from the installation itself, styles also inline (Vue
  binds `:style` attributes) and from Google Fonts, fonts from its CDN;
- API calls to the installation and to the other local installations the
  portal switches between (the front pins them to http://127.0.0.1:<port>,
  utils/session.js);
- the valuation-note preview in an <iframe> on a blob: URL;
- the microphone for script dictation, nothing else.

FastAPI's /docs page loads Swagger UI from a CDN: the content policy is left
off there, the other headers stay.
"""
from __future__ import annotations

CONTENT_SECURITY_POLICY = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self' http://127.0.0.1:* http://localhost:*",
    "frame-src 'self' blob:",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}

HSTS = "max-age=31536000"
_DOCS = ("/docs", "/redoc", "/openapi.json")


def security_headers(path: str, scheme: str) -> dict[str, str]:
    headers = dict(HEADERS)
    if not path.startswith(_DOCS):
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if scheme == "https":
        headers["Strict-Transport-Security"] = HSTS
    return headers


def install_security_headers(app) -> None:
    """Add the headers to every response of `app`, without overriding a
    header a route has set itself."""
    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        for name, value in security_headers(request.url.path, request.url.scheme).items():
            response.headers.setdefault(name, value)
        return response
