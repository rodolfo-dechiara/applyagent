# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately by email to
**kevlardb.commute085@simplelogin.com** (or via a GitHub private vulnerability
report on `rodolfo-dechiara/applyagent`). Do not open public issues for
security reports. You should receive an acknowledgment within 72 hours.

## Scope

You're Hired v0 is a candidate-side application builder. It processes job postings
and CV text pasted by the candidate, and calls the Mistral API with profile data
when `MISTRAL_API_KEY` is set. v0 never submits anything to third parties and
performs no outbound requests to user-supplied URLs.

## Supported versions

Only the latest commit on `main` is supported.

## Hardening baseline

See `docs/security-audit.md` for the full OWASP Top 10 / ASVS L1 audit. In short:

- Email verification is required before login (24 h, single-use tokens).
- Login, registration and verification-resend are rate limited (HTTP 429).
- Passwords are validated (length, common, numeric, similarity to username).
- Sessions are 1 h sliding, HttpOnly, SameSite=Lax, Secure in production.
- Password reset uses Django's signed token flow; password change requires the
  current password. Logout is POST-only.
- All app views are owner-scoped; cross-user access is a 404. Status changes are
  POST-only and validated.
- Security headers (CSP, HSTS, nosniff, frame-deny, referrer-policy) are set on
  every response; production fails fast without `DJANGO_SECRET_KEY` and
  `DJANGO_ALLOWED_HOSTS`.
- Security events are logged to the `core.security` logger; passwords and tokens
  are never logged.
- Runtime dependency is Django only; CI audits the locked dependencies with
  `pip-audit`.
