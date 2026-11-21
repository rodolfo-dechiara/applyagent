"""Django settings for the ApplyAgent project.

Glue configuration: environment-driven, SQLite, no external services required.
Demo mode is the default: without MISTRAL_API_KEY the agent layer returns
deterministic placeholder output instead of calling the Mistral API.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict (stdlib only; comments and blanks skipped)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _load_dotenv() -> None:
    """Load BASE_DIR/.env into the environment; real environment variables win."""
    for key, value in parse_env_file(BASE_DIR / ".env").items():
        os.environ.setdefault(key, value)


_load_dotenv()

DEBUG = os.environ.get("DEBUG", "True").lower() in ("1", "true", "yes")

# Fail fast in production: no silent dev fallbacks for the secret key or hosts
# (ASVS V14.4, OWASP A05).
_secret_key = os.environ.get("DJANGO_SECRET_KEY")
if _secret_key:
    SECRET_KEY = _secret_key
elif DEBUG:
    SECRET_KEY = "django-insecure-dev-key-change-me"
else:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is false.")

ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()
]
if not ALLOWED_HOSTS:
    if DEBUG:
        ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
    else:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set when DEBUG is false.")

# Behind a TLS-terminating proxy (Fly.io, Render, ...): trust the forwarded
# proto and declare the public origins so POST forms (CSRF) work over HTTPS.
_csrf_origins = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in _csrf_origins.split(",") if origin.strip()]

# --- Security headers, transport and cookies (ASVS V3/V9/V14, OWASP A05) ---
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Session hardening applies in dev too: 1 h sliding expiry, HttpOnly, Lax.
SESSION_COOKIE_AGE = 3600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
# Branded, user-friendly 403 instead of Django's bare CSRF failure page (the
# token rotates on every login, so stale tabs are an expected occurrence).
CSRF_FAILURE_VIEW = "core.views.csrf_failure"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "agent",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Deployed hosts set APPLYAGENT_DB to a path on a persistent volume.
        "NAME": os.environ.get("APPLYAGENT_DB", str(BASE_DIR / "db.sqlite3")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Logging: security events go to the core.security logger; warnings and errors
# (including django.request 500s and django.security.* CSRF rejections) go to
# the console, which `fly logs` captures in production.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "core.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "login"

# Feature flag: seed the public jobs board (/jobs/) with clearly-marked fake
# postings so demos never show an empty board. Off by default; enable with
# APPLYAGENT_DEMO_JOBS=true (e.g. on the demo deployment).
DEMO_JOBS_ENABLED = os.environ.get("APPLYAGENT_DEMO_JOBS", "false").lower() in (
    "1",
    "true",
    "yes",
)

# Agent / Mistral configuration. MISTRAL_API_KEY is optional: when it is not set,
# the whole application runs in deterministic demo mode.
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY") or None
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_TIMEOUT = float(os.environ.get("MISTRAL_TIMEOUT", "60"))

# Outbound email (verification links, password reset). When EMAIL_HOST is set we
# use Django's stdlib SMTP backend; otherwise emails are printed to stdout
# (console backend) — visible in runserver output and in `fly logs`.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "ApplyAgent <noreply@applyagent.local>")

# Rate limiting (fixed window; login is additionally keyed per account).
# The default cache is process-local: correct for one machine, move CACHES to a
# shared backend if the app ever scales out.
RATE_LIMIT_LOGIN_ATTEMPTS = int(os.environ.get("RATE_LIMIT_LOGIN_ATTEMPTS", "10"))
RATE_LIMIT_LOGIN_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "900"))
RATE_LIMIT_REGISTER_ATTEMPTS = int(os.environ.get("RATE_LIMIT_REGISTER_ATTEMPTS", "5"))
RATE_LIMIT_REGISTER_WINDOW_SECONDS = int(
    os.environ.get("RATE_LIMIT_REGISTER_WINDOW_SECONDS", "3600")
)
RATE_LIMIT_RESEND_ATTEMPTS = int(os.environ.get("RATE_LIMIT_RESEND_ATTEMPTS", "3"))
RATE_LIMIT_RESEND_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_RESEND_WINDOW_SECONDS", "3600"))
