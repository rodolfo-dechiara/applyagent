"""Security-event logging and small security helpers.

Passwords, tokens and other secrets are NEVER logged.
"""

import logging

from django.http import HttpRequest

logger = logging.getLogger("core.security")


def client_ip(request: HttpRequest) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")
