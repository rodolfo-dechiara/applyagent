"""Email-or-username login.

Prod incident: users typed their email into the username field and login
failed with the correct password, because Django's ModelBackend only matches
`username`. These tests lock in that the login field accepts either.
Written red before the backend existed.
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.tests.utils import PASSWORD

EMAIL = "youre-hired.episode421@passmail.net"


class EmailLoginTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="episode421", email=EMAIL, password=PASSWORD)

    def login(self, username: str, password: str = PASSWORD):
        return self.client.post(reverse("login"), {"username": username, "password": password})

    def test_login_with_username_works(self) -> None:
        response = self.login("episode421")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:dashboard"))

    def test_login_with_email_works(self) -> None:
        response = self.login(EMAIL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:dashboard"))

    def test_login_with_email_in_different_case_works(self) -> None:
        response = self.login(EMAIL.upper())
        self.assertEqual(response.status_code, 302)

    def test_wrong_password_with_email_fails_generically(self) -> None:
        response = self.login(EMAIL, password="Wr0ng!Pass99")
        self.assertEqual(response.status_code, 200)  # form re-rendered, no redirect
        self.assertContains(response, "correct")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_unverified_account_cannot_login_even_with_email(self) -> None:
        User.objects.create_user(
            username="unverified",
            email="unverified@example.com",
            password=PASSWORD,
            is_active=False,
        )
        response = self.login("unverified@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_email_shared_by_two_accounts_is_refused(self) -> None:
        # rodolfo/rodolfotest share an email in prod: ambiguous email login must
        # fail closed, while the username still works.
        User.objects.create_user(username="second", email=EMAIL, password=PASSWORD, is_active=True)
        response = self.login(EMAIL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        response = self.login("episode421")
        self.assertEqual(response.status_code, 302)

    def test_login_page_labels_field_username_or_email(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Username or email")
