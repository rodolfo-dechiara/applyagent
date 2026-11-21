"""Security response headers — Django only, no extra dependency."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

# Alpine.js (CDN build) evaluates expressions with new Function and the Tailwind
# Play CDN compiles in-browser, so script-src needs 'unsafe-eval' while the
# no-build-step CDN constraint holds. Everything else is locked down, and no
# user-supplied HTML is ever rendered unescaped (covered by tests). If the CDN
# constraint is ever lifted, switch to compiled assets and drop 'unsafe-eval'.
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.tailwindcss.com https://cdn.jsdelivr.net 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net "
    "https://fonts.googleapis.com; "
    "img-src 'self' data:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"


class SecurityHeadersMiddleware:
    """Adds CSP + hardening headers to every response.

    /admin/ is exempt from CSP (Django's admin is not fully CSP-clean); it stays
    protected by Django auth and X-Frame-Options: DENY.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.headers["Content-Security-Policy"] = CSP_POLICY
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response
