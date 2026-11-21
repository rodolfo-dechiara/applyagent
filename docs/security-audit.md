# ApplyAgent — Security Audit Report

**Date:** 2026-11-21
**Scope:** the whole v0 codebase (`config/`, `core/`, `agent/`), deployment config
(`Dockerfile`, `fly.toml`, `.github/workflows/ci.yml`), and the live Fly.io deployment.
**Method:** manual code review mapped against the **OWASP Top 10 (2021)** and the
**OWASP ASVS 5.0**, targeting **at least Level 1**. Every fix below is driven by a
failing test first (project TDD rule) and committed per behavior.
**Runtime constraint honored throughout:** Django is the only runtime dependency;
the Mistral client uses stdlib `urllib` only; no JS build step.

## Summary of findings

| # | Finding | OWASP Top 10 | ASVS 5.0 | Severity | Status |
|---|---------|--------------|----------|----------|--------|
| F1 | Registration did not verify the email address; anyone could register with any address and log in immediately | A07 | V2.1 | High | **Fixed** — `EmailVerification` token (24 h TTL), account `is_active=False` until verified, resend endpoint that never reveals whether an address is registered |
| F2 | No rate limiting / lockout on login, registration, verification resend (brute force, enumeration, mail bombing) | A07 | V2.2 | High | **Fixed** — fixed-window limiter on Django's cache, per-IP (+ per-account on login), HTTP 429 + security log |
| F3 | No security headers: no CSP, no HSTS, no `Secure`/`SameSite` cookie flags in production, `X-Content-Type-Options` unset | A05 | V9.1, V14.4 | High | **Fixed** — `SecurityHeadersMiddleware` (CSP, Permissions-Policy, CORP), `SECURE_*` settings in prod, secure cookies |
| F4 | `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` silently fell back to dev values when `DEBUG=False` | A05 | V14.4 | High | **Fixed** — fail-fast `ImproperlyConfigured` in production mode |
| F5 | No session timeout; default 2-week sessions | A07 | V3.3 | Medium | **Fixed** — 1 h sliding expiry (`SESSION_COOKIE_AGE`, `SESSION_SAVE_EVERY_REQUEST`), HttpOnly + SameSite=Lax cookies |
| F6 | Password reset / change flows not wired (no templates), so account recovery was impossible without admin | A07 | V2.1, V7.4 | Medium | **Fixed** — Django auth views + templates, tokenized reset, change requires current password |
| F7 | No security-event logging (login success/failure, registration, verification, rate-limit hits) | A09 | V7.1, V7.3 | Medium | **Fixed** — `core.security` logger + auth signals + `LOGGING` config; secrets (passwords, tokens) are never logged |
| F8 | `source_url` rendered as `<a href>` with no scheme allowlist (`ftp:` allowed); no length caps on free-text inputs | A03/A05 | V5.1, V5.2 | Medium | **Fixed** — `URLValidator(schemes=["http","https"])` on the model, `max_length` caps in forms, output-escaping regression tests |
| F9 | No password-strength test coverage (validators were configured but untested) | A07 | V2.1 | Low | **Fixed** — tests lock in all four `AUTH_PASSWORD_VALIDATORS` |
| F10 | No dependency vulnerability scanning in CI | A06 | V14.2 | Low | **Fixed** — `pip-audit` job on the locked runtime deps |
| F11 | Generic login errors were not regression-tested (user enumeration) | A07 | V2.1 | Low | **Fixed** — test asserts identical error for unknown user vs wrong password |
| F12 | Logout not verified as POST-only | A07 | V3.7 | Low | **Fixed** — test asserts GET logout is 405 |

Already OK at audit time (verified, regression tests added where cheap):

- **A01 Broken Access Control:** every application view filters by `request.user`
  (cross-user 404 tests exist for detail/regenerate/edit/status/delete); all app
  views are `LoginRequiredMixin`; status changes are POST-only and validated against
  the choices; anonymous users are redirected to login.
- **A03 Injection:** ORM only, no raw SQL anywhere; templates rely on Django
  autoescaping (now locked by escaping tests with `<script>`/`<img onerror>` payloads).
- **A10 SSRF:** no outbound requests to user-controlled URLs — postings arrive by
  paste and `source_url` is only stored/rendered (now scheme-allowlisted), never fetched.
- **A02 Cryptographic failures:** `SECRET_KEY` from env; TLS enforced by Fly
  (`force_https`) plus `SECURE_SSL_REDIRECT` + HSTS in prod; secrets never committed
  (`.env` gitignored, `.dockerignore` excludes it; the Mistral key exists only in
  `.env` and as a Fly secret).
- **A08 Integrity:** `uv.lock` committed, `uv sync --locked` in CI and Docker build.

## OWASP Top 10 (2021) mapping

| Category | Status | Evidence |
|----------|--------|----------|
| A01 Broken Access Control | Pass | `core/tests/test_ownership.py`, `LoginRequiredMixin` everywhere, POST-only transitions |
| A02 Cryptographic Failures | Pass | env-driven `SECRET_KEY` (fail-fast in prod), HTTPS + HSTS on Fly, secure cookies, no secrets in git |
| A03 Injection | Pass | ORM only; autoescaping regression tests (`test_input_security.py`); URL scheme allowlist |
| A04 Insecure Design | Pass (L1) | email verification, rate limiting, generic auth errors, "agent drafts, human decides" keeps a human in the loop |
| A05 Security Misconfiguration | Pass | prod fail-fast config, security headers middleware, DEBUG off on Fly, `pip-audit` in CI |
| A06 Vulnerable Components | Pass | locked deps + `pip-audit` CI job (runtime = Django only; gunicorn is image-build-only, see residual risks) |
| A07 Identification & Authentication | Pass | verified registration, password validators, rate limiting, session timeout, POST-only logout, tokenized password reset |
| A08 Software & Data Integrity | Pass | `uv.lock`, `--locked` sync, no unsigned code paths |
| A09 Logging & Monitoring | Pass | `core.security` logger for auth/registration/verification/rate-limit events; errors to console (captured by `fly logs`) |
| A10 SSRF | Pass | no fetches of user-supplied URLs; LLM call goes only to the fixed Mistral endpoint |

## ASVS 5.0 Level 1 — control coverage

| ASVS chapter | L1 controls implemented |
|--------------|-------------------------|
| V2 Authentication | V2.1.1 email verification at registration (24 h token, single use); V2.1.x password validators (similarity, min length, common, numeric); V2.2.1 rate limiting on login/register/resend with 429; generic authentication errors (no enumeration); tokenized password reset; password change requires current password; logout invalidates the session (POST-only) |
| V3 Session | V3.1/3.2 session cookie HttpOnly + SameSite=Lax (+ `Secure` in prod); V3.3 1 h sliding expiry; V3.4 session key rotated on login (Django built-in); V3.7 POST-only logout |
| V4 Access Control | owner-scoped querysets (404 for other users), login required on all app views, POST-only + validated status transitions, default-deny (anonymous → login redirect) |
| V5 Input Validation | form validation on all inputs, `max_length` caps on free text, URL scheme allowlist, output encoding via autoescaping (tested), CSRF on every POST (tested with `enforce_csrf_checks`) |
| V7 Error Handling & Logging | no stack traces in prod (`DEBUG=False`), security events logged to `core.security`, no secrets in logs |
| V9 Communication | TLS enforced (Fly `force_https` + `SECURE_SSL_REDIRECT`), HSTS 1 year in prod, `nosniff`, `Referrer-Policy: same-origin` |
| V14 Configuration | fail-fast prod config (secret key, allowed hosts), security headers, locked dependencies, CSP, `pip-audit` in CI |

L2/L3 items deliberately out of scope for v0 (see residual risks).

## Residual risks / recommendations (not L1 blockers)

1. **Rate limiting uses Django's local-memory cache** — correct for the single-machine
   Fly deployment; if the app ever scales to multiple machines, move `CACHES` to a
   shared backend (Redis) or the limiter becomes per-machine.
2. **Email delivery:** without `EMAIL_HOST*` the console backend prints emails to
   stdout (visible in `fly logs`) — fine for demo, not for real users. Set SMTP env
   vars for production delivery.
3. **CSP contains `'unsafe-eval'` in `script-src`** because the mandated CDN stack
   (Alpine.js 3 — no CSP build published for 3.14.x — and the Tailwind Play CDN)
   evaluates code in the browser. Mitigations in place: `default-src 'self'`,
   `frame-ancestors 'none'`, `object-src 'none'`, `form-action 'self'`, and *no
   user-supplied HTML is ever rendered unescaped* (tested). If the no-build-step
   constraint is ever relaxed, switch to compiled assets and drop `'unsafe-eval'`.
4. **CSP is not applied to `/admin/`** (Django admin is not fully CSP-clean); admin is
   protected by Django auth + `X-Frame-Options: DENY` instead. Consider disabling
   admin on the public deployment.
5. **`gunicorn` is installed at image build time only**, so `pip-audit` (locked
   runtime deps) does not cover it. It is pinned by the Dockerfile; add it to the dev
   dependency group if you want it audited too.
6. **SQLite on a single Fly volume** — fine for v0; move to Postgres for multi-writer
   workloads (and then item 1).
7. Consider enabling GitHub Dependabot for the repo, and `SECURE_HSTS_PRELOAD` only
   after submitting the domain to the HSTS preload list.

## Verification

```
uv sync
uv run python manage.py makemigrations
uv run python manage.py migrate
env -u MISTRAL_API_KEY uv run python manage.py test   # demo mode, no key needed
uv run ruff check . && uv run ruff format --check .
uv run pyrefly check
uvx pre-commit run --all-files
```

Live checks on https://applyagents.fly.dev: security headers present on every
response, register → verification email in `fly logs` → verify → login → full loop.
