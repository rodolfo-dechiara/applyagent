"""Security-event logging. Passwords, tokens and other secrets are NEVER logged."""

import logging

logger = logging.getLogger("core.security")
