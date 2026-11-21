"""Registration + email verification (ASVS V2.1, OWASP A07).

Written red before the implementation: registering must NOT log the user in;
the account stays inactive until the emailed single-use token is visited.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import EmailVerification
from core.tests.utils import PASSWORD, register, register_and_verify, verify_latest


class RegistrationVerificationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()  # rate-limit buckets must not leak between tests

    def test_register_page_has_email_field(self) -> None:
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"')

    def test_register_creates_inactive_user_and_redirects_to_done_page(self) -> None:
        response = register(self.client, username="newbie")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("register_done"))
        user = User.objects.get(username="newbie")
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "newbie@example.com")
        # Not logged in yet.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_register_sends_verification_email_with_link(self) -> None:
        register(self.client, username="newbie")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["newbie@example.com"])
        self.assertIn("/accounts/verify/", message.body)
        self.assertTrue(EmailVerification.objects.filter(user__username="newbie").exists())

    def test_register_requires_email(self) -> None:
        response = self.client.post(
            reverse("register"),
            {"username": "newbie", "password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_unverified_user_cannot_log_in(self) -> None:
        register(self.client, username="newbie")
        response = self.client.post(reverse("login"), {"username": "newbie", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)  # form error, not a redirect
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)  # still bounced to login

    def test_verify_link_activates_user_and_logs_in(self) -> None:
        register(self.client, username="newbie")
        response = verify_latest(self.client)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:dashboard"))
        user = User.objects.get(username="newbie")
        self.assertTrue(user.is_active)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        # Token is single-use.
        self.assertFalse(EmailVerification.objects.filter(user=user).exists())

    def test_verify_with_unknown_token_is_404(self) -> None:
        response = self.client.get(reverse("verify_email", args=["no-such-token"]))
        self.assertEqual(response.status_code, 404)

    def test_expired_token_is_rejected(self) -> None:
        register(self.client, username="newbie")
        verification = EmailVerification.objects.get(user__username="newbie")
        EmailVerification.objects.filter(pk=verification.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        response = verify_latest(self.client)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(username="newbie").is_active)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_resend_sends_new_email_for_unverified_user(self) -> None:
        register(self.client, username="newbie")
        first_token = EmailVerification.objects.get(user__username="newbie").token
        response = self.client.post(reverse("resend_verification"), {"email": "newbie@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        new_token = EmailVerification.objects.get(user__username="newbie").token
        self.assertNotEqual(first_token, new_token)

    def test_resend_never_reveals_whether_email_is_registered(self) -> None:
        register(self.client, username="newbie")
        known = self.client.post(reverse("resend_verification"), {"email": "newbie@example.com"})
        outbox_after_known = len(mail.outbox)
        unknown = self.client.post(reverse("resend_verification"), {"email": "ghost@example.com"})
        # Same response, no extra email for the unknown address.
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known["Location"], unknown["Location"])
        self.assertEqual(len(mail.outbox), outbox_after_known)

    def test_resend_for_verified_user_sends_nothing(self) -> None:
        register_and_verify(self.client, username="newbie")
        outbox_len = len(mail.outbox)
        self.client.post(reverse("resend_verification"), {"email": "newbie@example.com"})
        self.assertEqual(len(mail.outbox), outbox_len)

    def test_weak_passwords_are_rejected(self) -> None:
        for weak in ["password", "12345678", "newbie123", "short"]:
            with self.subTest(password=weak):
                response = register(self.client, username="newbie", password=weak)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(User.objects.filter(username="newbie").exists())


class LoginEnumerationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_unknown_user_and_wrong_password_get_the_same_generic_error(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD)
        wrong_password = self.client.post(
            reverse("login"), {"username": "bob", "password": "Wrong!Pass1"}
        )
        unknown_user = self.client.post(
            reverse("login"), {"username": "ghost", "password": "Wrong!Pass1"}
        )
        self.assertEqual(wrong_password.status_code, 200)
        self.assertEqual(unknown_user.status_code, 200)
        self.assertEqual(
            wrong_password.context["form"].non_field_errors(),
            unknown_user.context["form"].non_field_errors(),
        )

    def test_logout_requires_post(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD, is_active=True)
        self.client.force_login(User.objects.get(username="bob"))
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
