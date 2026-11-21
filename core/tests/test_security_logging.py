"""Security-event logging (ASVS V7, OWASP A09): login success/failure,
registration, email verification and rate-limit hits are logged to the
core.security logger; secrets are never logged."""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.utils import PASSWORD, register, verify_latest


class SecurityLoggingTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_logging_config_defines_core_security_logger(self) -> None:
        logger_config = settings.LOGGING["loggers"]["core.security"]
        self.assertEqual(logger_config["level"], "INFO")

    def test_failed_login_is_logged_as_warning(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD)
        with self.assertLogs("core.security", level="WARNING") as captured:
            self.client.post(reverse("login"), {"username": "bob", "password": "Wrong!Pass1"})
        self.assertTrue(any("login_failed" in line for line in captured.output))
        # The password must never appear in the logs.
        self.assertFalse(any("Wrong!Pass1" in line for line in captured.output))

    def test_successful_login_is_logged(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD)
        with self.assertLogs("core.security", level="INFO") as captured:
            self.client.post(reverse("login"), {"username": "bob", "password": PASSWORD})
        self.assertTrue(any("login_success" in line for line in captured.output))

    def test_registration_and_verification_are_logged(self) -> None:
        with self.assertLogs("core.security", level="INFO") as captured:
            register(self.client, username="newbie")
            verify_latest(self.client)
        self.assertTrue(any("register" in line for line in captured.output))
        self.assertTrue(any("email_verified" in line for line in captured.output))

    @override_settings(RATE_LIMIT_LOGIN_ATTEMPTS=1, RATE_LIMIT_LOGIN_WINDOW_SECONDS=900)
    def test_rate_limit_hit_is_logged(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD)
        self.client.post(reverse("login"), {"username": "bob", "password": "Wrong!Pass1"})
        with self.assertLogs("core.security", level="WARNING") as captured:
            self.client.post(reverse("login"), {"username": "bob", "password": "Wrong!Pass1"})
        self.assertTrue(any("rate_limit_hit" in line for line in captured.output))
