"""Production configuration must fail fast and turn on the SECURE_* flags
(ASVS V14.4, OWASP A05). Settings are reloaded in-process with a scrubbed
environment (and .env parsing mocked out) so the real .env cannot interfere."""

import importlib
import os
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

import config.settings as settings_module


def load_settings(env: dict[str, str]) -> SimpleNamespace:
    """Reload config.settings with a scrubbed environment, snapshot the uppercase
    settings, then always restore the original module state."""
    saved = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(env)
        with mock.patch.object(settings_module, "parse_env_file", return_value={}):
            importlib.reload(settings_module)
            return SimpleNamespace(
                **{
                    name: getattr(settings_module, name)
                    for name in dir(settings_module)
                    if name.isupper()
                }
            )
    finally:
        os.environ.clear()
        os.environ.update(saved)
        with mock.patch.object(settings_module, "parse_env_file", return_value={}):
            importlib.reload(settings_module)


class ProdSettingsTests(SimpleTestCase):
    def test_prod_without_secret_key_fails_fast(self) -> None:
        with self.assertRaises(ImproperlyConfigured) as ctx:
            load_settings({"DEBUG": "False", "DJANGO_ALLOWED_HOSTS": "example.com"})
        self.assertIn("DJANGO_SECRET_KEY", str(ctx.exception))

    def test_prod_without_allowed_hosts_fails_fast(self) -> None:
        with self.assertRaises(ImproperlyConfigured) as ctx:
            load_settings({"DEBUG": "False", "DJANGO_SECRET_KEY": "test-secret"})
        self.assertIn("DJANGO_ALLOWED_HOSTS", str(ctx.exception))

    def test_prod_enables_transport_and_cookie_flags(self) -> None:
        module = load_settings(
            {
                "DEBUG": "False",
                "DJANGO_SECRET_KEY": "test-secret",
                "DJANGO_ALLOWED_HOSTS": "example.com",
            }
        )
        self.assertTrue(module.SECURE_SSL_REDIRECT)
        self.assertEqual(module.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(module.SESSION_COOKIE_SECURE)
        self.assertTrue(module.CSRF_COOKIE_SECURE)
        self.assertEqual(module.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertEqual(module.ALLOWED_HOSTS, ["example.com"])

    def test_dev_mode_keeps_safe_defaults_without_prod_flags(self) -> None:
        module = load_settings({"DEBUG": "True"})
        self.assertFalse(getattr(module, "SECURE_SSL_REDIRECT", False))
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", vars(module))
        # Session hardening applies in dev too.
        self.assertEqual(module.SESSION_COOKIE_AGE, 3600)
        self.assertTrue(module.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(module.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(module.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(module.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertTrue(module.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(module.SECURE_REFERRER_POLICY, "same-origin")
