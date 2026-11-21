"""Fixed-window rate limiting on top of Django's cache — no extra dependencies.

The default cache is process-local, which is correct for the single-machine
deployment; if the app ever scales to multiple machines, move CACHES to a
shared backend or the counters become per-machine.

Limits/windows are read from settings on every hit so tests can override them:
RATE_LIMIT_<SCOPE>_ATTEMPTS and RATE_LIMIT_<SCOPE>_WINDOW_SECONDS.
"""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from core.security import client_ip, logger

F = TypeVar("F", bound=Callable[..., HttpResponse])


def is_allowed(scope: str, identifier: str, default_limit: int, default_window: int) -> bool:
    """Record one hit for (scope, identifier) in the current fixed window.

    Returns False when the limit is already exhausted (the hit is still not
    counted past the limit, so the window is not extended by floods).
    """
    limit = int(getattr(settings, f"RATE_LIMIT_{scope.upper()}_ATTEMPTS", default_limit))
    window = int(getattr(settings, f"RATE_LIMIT_{scope.upper()}_WINDOW_SECONDS", default_window))
    if limit <= 0:  # 0 disables the limiter (useful in tests)
        return True
    key = f"ratelimit:{scope}:{identifier}:{int(time.time()) // window}"
    count = cache.get(key, 0)
    if count >= limit:
        return False
    cache.set(key, count + 1, window + 60)
    return True


def rate_limited(
    scope: str,
    default_limit: int,
    default_window: int,
    ident: Callable[[HttpRequest], str] | None = None,
) -> Callable[[F], F]:
    """Class- or function-based decorator: wrap ``dispatch``/the view and answer
    HTTP 429 once the window's limit is exhausted."""

    def decorator(view: F) -> F:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            identifier = ident(request) if ident is not None else client_ip(request)
            if not is_allowed(scope, identifier, default_limit, default_window):
                logger.warning("rate_limit_hit scope=%s identifier=%s", scope, identifier)
                return HttpResponse("Too many attempts — please try again later.", status=429)
            return view(request, *args, **kwargs)

        return cast(F, wrapper)

    return decorator
