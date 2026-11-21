"""Password reset (signed, expiring, single-use tokens; no account enumeration)
and password change (requires the current password) — ASVS V2.1/V7.4, A07."""

import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.tests.utils import PASSWORD

NEW_PASSWORD = "N3w!Passw0rd42"
RESET_LINK_RE = re.compile(r"(/accounts/password-reset/[^\s]+)")


class PasswordResetTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            username="bob", password=PASSWORD, email="bob@example.com"
        )

    def request_reset(self, email: str):
        return self.client.post(reverse("password_reset"), {"email": email})

    def test_reset_request_sends_signed_link(self) -> None:
        response = self.request_reset("bob@example.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@example.com"])
        self.assertRegex(str(mail.outbox[0].body), RESET_LINK_RE)

    def test_unknown_email_gets_same_response_and_no_email(self) -> None:
        known = self.request_reset("bob@example.com")
        outbox_len = len(mail.outbox)
        unknown = self.request_reset("ghost@example.com")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known["Location"], unknown["Location"])
        self.assertEqual(len(mail.outbox), outbox_len)

    def extract_reset_path(self) -> str:
        match = RESET_LINK_RE.search(str(mail.outbox[-1].body))
        assert match, "no reset link in email body"
        return match.group(1)

    def test_full_reset_flow_changes_password(self) -> None:
        self.request_reset("bob@example.com")
        response = self.client.get(self.extract_reset_path())
        self.assertEqual(response.status_code, 302)  # to the set-password session URL
        response = self.client.post(
            response["Location"],
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        # Old password no longer works, new one does.
        self.assertEqual(
            self.client.post(
                reverse("login"), {"username": "bob", "password": PASSWORD}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                reverse("login"), {"username": "bob", "password": NEW_PASSWORD}
            ).status_code,
            302,
        )

    def test_reset_rejects_weak_new_password(self) -> None:
        self.request_reset("bob@example.com")
        response = self.client.get(self.extract_reset_path())
        response = self.client.post(
            response["Location"],
            {"new_password1": "password", "new_password2": "password"},
        )
        self.assertEqual(response.status_code, 200)  # form errors, not a redirect
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_reset_link_is_single_use(self) -> None:
        self.request_reset("bob@example.com")
        path = self.extract_reset_path()
        response = self.client.get(path)
        self.client.post(
            response["Location"],
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        # Visiting the original emailed link again must not work.
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid", status_code=200)


class PasswordChangeTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="bob", password=PASSWORD)
        self.client.force_login(self.user)

    def test_change_requires_the_current_password(self) -> None:
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "Wrong!Old1",
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_change_with_correct_current_password(self) -> None:
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_change_page_requires_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
