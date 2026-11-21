"""Authentication backend that accepts the username OR the email address in
the login form's single "username" field.

Prod incident: candidates typed their email and login failed even with the
correct password, because ModelBackend only matches `username`. If several
accounts share one email address the match is ambiguous, so email login is
refused (fail closed) — the username always works in that case.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.http import HttpRequest


class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: object,
    ) -> AbstractBaseUser | None:
        if username is None or password is None:
            return None
        user_model = get_user_model()
        matches = user_model.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        )
        if matches.count() != 1:
            # No match, or an email shared by several accounts: refuse, and run
            # a dummy password hash so timing does not reveal which case it was.
            user_model().set_password(password)
            return None
        user = matches.first()
        if user is not None and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
