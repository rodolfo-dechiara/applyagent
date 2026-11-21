"""Security response headers (ASVS V9/V14, OWASP A05) and cookie flags (V3)."""

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from core.middleware import CSP_POLICY, SecurityHeadersMiddleware
from core.tests.utils import PASSWORD


class SecurityHeadersMiddlewareTests(SimpleTestCase):
    def respond(self, path: str) -> HttpResponse:
        middleware = SecurityHeadersMiddleware(lambda request: HttpResponse("ok"))
        return middleware(RequestFactory().get(path))

    def test_csp_header_is_set(self) -> None:
        response = self.respond("/")
        csp = response.headers["Content-Security-Policy"]
        self.assertEqual(csp, CSP_POLICY)
        for directive in (
            "default-src 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "form-action 'self'",
            "base-uri 'self'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
        ):
            self.assertIn(directive, csp)

    def test_permissions_policy_and_corp_headers(self) -> None:
        response = self.respond("/")
        self.assertEqual(
            response.headers["Permissions-Policy"], "camera=(), microphone=(), geolocation=()"
        )
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")

    def test_admin_is_exempt_from_csp_but_keeps_other_headers(self) -> None:
        response = self.respond("/admin/login/")
        self.assertNotIn("Content-Security-Policy", response.headers)
        self.assertIn("Permissions-Policy", response.headers)


class SecurityHeadersIntegrationTests(TestCase):
    def test_login_page_carries_security_headers(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    def test_session_cookie_is_httponly_and_lax(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD)
        response = self.client.post(reverse("login"), {"username": "bob", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        cookie = response.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_csrf_token_cookie_is_httponly(self) -> None:
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("login"))
        self.assertTrue(response.cookies["csrftoken"]["httponly"])
