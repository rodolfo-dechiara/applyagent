"""Shared helpers for auth-flow tests (registration + email verification)."""

import re

from django.core import mail
from django.test import Client
from django.urls import reverse

PASSWORD = "Str0ng!Pass99"
VERIFY_LINK_RE = re.compile(r"/accounts/verify/([A-Za-z0-9_\-]+)/")


def register(
    client: Client,
    username: str = "alice",
    email: str | None = None,
    password: str = PASSWORD,
    role: str = "candidate",
):
    """POST the registration form (email is required since verification exists)."""
    return client.post(
        reverse("register"),
        {
            "username": username,
            "email": email if email is not None else f"{username}@example.com",
            "password1": password,
            "password2": password,
            "role": role,
        },
    )


def extract_verify_token() -> str:
    """Pull the verification token out of the most recent email in the outbox."""
    assert mail.outbox, "expected at least one email in the test outbox"
    body = str(mail.outbox[-1].body)
    match = VERIFY_LINK_RE.search(body)
    assert match, f"no verification link found in email body: {body!r}"
    return match.group(1)


def verify_latest(client: Client):
    """GET the verification link from the most recent email."""
    return client.get(reverse("verify_email", args=[extract_verify_token()]))


def register_and_verify(client: Client, username: str = "alice", password: str = PASSWORD):
    """Full happy path: register, then verify via the emailed link (logs the user in)."""
    response = register(client, username=username, password=password)
    assert response.status_code == 302, f"register failed: {response.status_code}"
    return verify_latest(client)
