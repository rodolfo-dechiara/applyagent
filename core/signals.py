"""Auth-event receivers for the security log. Passwords, tokens and other
secrets are NEVER logged — only usernames and IPs."""

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from django.http import HttpRequest

from core.security import client_ip, logger


@receiver(user_logged_in)
def log_login_success(
    sender: Any, request: HttpRequest, user: AbstractBaseUser, **kwargs: Any
) -> None:
    logger.info("login_success user=%s ip=%s", user.get_username(), client_ip(request))


@receiver(user_login_failed)
def log_login_failure(
    sender: Any, credentials: dict[str, Any] | None, request: HttpRequest, **kwargs: Any
) -> None:
    username = (credentials or {}).get("username", "")
    logger.warning("login_failed username=%s ip=%s", username, client_ip(request))
