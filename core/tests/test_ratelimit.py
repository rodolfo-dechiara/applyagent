"""Rate limiting on auth endpoints (ASVS V2.2.1, OWASP A07): brute-force and
enumeration protection via fixed-window counters on Django's cache, HTTP 429
when exhausted, and a security-log entry on every hit."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.utils import PASSWORD, register


@override_settings(RATE_LIMIT_LOGIN_ATTEMPTS=3, RATE_LIMIT_LOGIN_WINDOW_SECONDS=900)
class LoginRateLimitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="bob", password=PASSWORD)

    def login_attempt(self, **extra):
        return self.client.post(
            reverse("login"),
            {"username": "bob", "password": "Wrong!Pass1"},
            **extra,
        )

    def test_login_is_blocked_with_429_after_the_limit(self) -> None:
        for _ in range(3):
            response = self.login_attempt()
            self.assertEqual(response.status_code, 200)  # normal form error
        response = self.login_attempt()
        self.assertEqual(response.status_code, 429)

    def test_correct_password_within_the_limit_still_works(self) -> None:
        self.login_attempt()
        self.login_attempt()
        response = self.client.post(reverse("login"), {"username": "bob", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_limit_is_scoped_per_ip(self) -> None:
        for _ in range(3):
            self.login_attempt()
        response = self.login_attempt(REMOTE_ADDR="10.9.9.9")
        self.assertEqual(response.status_code, 200)  # different IP, fresh bucket

    def test_limit_is_scoped_per_account(self) -> None:
        for _ in range(3):
            self.login_attempt()
        response = self.client.post(
            reverse("login"), {"username": "someoneelse", "password": "Wrong!Pass1"}
        )
        self.assertEqual(response.status_code, 200)  # different account, fresh bucket

    def test_get_requests_do_not_consume_the_budget(self) -> None:
        for _ in range(10):
            response = self.client.get(reverse("login"))
            self.assertEqual(response.status_code, 200)
        # POSTs still get the full budget afterwards.
        for _ in range(3):
            self.assertEqual(self.login_attempt().status_code, 200)
        self.assertEqual(self.login_attempt().status_code, 429)

    def test_rate_limit_hit_is_logged(self) -> None:
        for _ in range(3):
            self.login_attempt()
        with self.assertLogs("core.security", level="WARNING") as captured:
            self.login_attempt()
        self.assertTrue(any("rate_limit_hit" in line for line in captured.output))


@override_settings(RATE_LIMIT_REGISTER_ATTEMPTS=2, RATE_LIMIT_REGISTER_WINDOW_SECONDS=3600)
class RegisterRateLimitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_register_is_blocked_with_429_after_the_limit(self) -> None:
        self.assertEqual(register(self.client, username="u1").status_code, 302)
        self.assertEqual(register(self.client, username="u2").status_code, 302)
        response = register(self.client, username="u3")
        self.assertEqual(response.status_code, 429)


@override_settings(RATE_LIMIT_RESEND_ATTEMPTS=2, RATE_LIMIT_RESEND_WINDOW_SECONDS=3600)
class ResendRateLimitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_resend_is_blocked_with_429_after_the_limit(self) -> None:
        url = reverse("resend_verification")
        self.assertEqual(self.client.post(url, {"email": "a@example.com"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"email": "b@example.com"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"email": "c@example.com"}).status_code, 429)
