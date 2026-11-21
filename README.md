# You're Hired v0

A candidate-side agentic job application builder — the first half of an
"AI-augmented LinkedIn". You keep one master profile, paste a job posting,
and the agent drafts the full application package: tailored summary, cover
letter, screening answers, match score with reasons, and red flags.

**The agent drafts, the human decides.** Nothing is final until you review
and edit it. V0 only prepares and tracks applications — it never submits
anything anywhere.

## Stack

- Django 5 + SQLite. Server-rendered only.
- HTMX 2 + Alpine.js 3 + Tailwind via CDN — no JS build step, no node.
- Runtime dependency: **Django only**. The Mistral client (`agent/llm.py`)
  uses stdlib `urllib` against `https://api.mistral.ai/v1/chat/completions`
  — no SDK, no `requests`.
- Everything is managed with **uv** — never pip, never bare `python`.

## Quickstart

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Open http://127.0.0.1:8000/ — register, fill in your master profile, paste a
job posting, and review the generated package on the application page.

Configuration is via environment variables (see `.env.example`):

| Variable            | Required | Default                 |
| ------------------- | -------- | ----------------------- |
| `MISTRAL_API_KEY`   | no       | unset → demo mode       |
| `MISTRAL_MODEL`     | no       | `mistral-small-latest`  |
| `MISTRAL_TIMEOUT`   | no       | `60`                    |
| `DJANGO_SECRET_KEY` | prod     | dev default             |
| `DEBUG`             | no       | `True`                  |

## Demo mode

With **no `MISTRAL_API_KEY` in the environment** the full loop works end to
end with zero network calls: every generated field is deterministic and
clearly marked `DEMO OUTPUT: ...`, `agent_mode` is `demo`, and the match
score is a deterministic skill-keyword overlap. This is what CI runs.
Set `MISTRAL_API_KEY` to get real agent-drafted packages; the system prompt
forbids inventing facts about the candidate — anything the profile lacks
goes into `red_flags`, never into the cover letter.

## Public job board + demo postings flag

`/jobs/` is a **public** board of postings whose owner ticked "list on the
public job board" when pasting (private by default — everyone else gets a
404 on a private posting, same ownership rule as applications). Anyone can
browse it anonymously; a logged-in candidate can POST "Build my application
for this job" on a posting, which clones the posting privately to them and
generates the agent package immediately (the original stays untouched).

For demos, set **`APPLYAGENT_DEMO_JOBS=true`** (`DEMO_JOBS_ENABLED`): the
board then seeds itself on first view with clearly-marked fake postings
(`DEMO POSTING: ...` in the description), owned by a login-less `demo-board`
system account. Seeding is idempotent and a no-op when the flag is off —
so CI and local dev never see fake data. On Fly.io:
`fly secrets set APPLYAGENT_DEMO_JOBS=true -a applyagents`.

## Development

```bash
uv run python manage.py test                     # full suite incl. e2e (demo mode)
uv run python manage.py test --exclude-tag e2e   # unit/integration only
uv run python manage.py test core.tests.test_e2e # e2e only (needs the browser:
                                                 #   uv run playwright install --with-deps chromium)
uv run ruff check .                   # lint
uv run ruff format --check .          # format check
uv run pyrefly check                  # type check
uvx pre-commit run --all-files        # hooks (ruff, ruff-format, pyrefly)
```

E2E tests (`core/tests/test_e2e.py`) drive real Chromium via Playwright
(pip-installed dev dependency — no node/npm) against a live Django server:
the full register → verify-email → profile → paste-job → HTMX-regenerate →
edit → status → delete loop on a 390px mobile viewport (asserting no
horizontal overflow and a working hamburger menu) and a 1280px desktop
viewport, a board apply-from-demo-posting flow with the demo-jobs flag on,
plus overflow checks on all auth pages and `/jobs/` at 360px.

CI (`.github/workflows/ci.yml`) runs lint, types, tests (`--exclude-tag e2e`),
a dedicated `e2e` job (installs Chromium, runs the e2e suite), and a
`pip-audit` dependency scan on pushes and PRs to `main` via the official
`astral-sh/setup-uv` action.

## Security

See [SECURITY.md](SECURITY.md) and the full audit in
[docs/security-audit.md](docs/security-audit.md) (OWASP Top 10 2021 +
OWASP ASVS 5.0, targeting Level 1). Baseline:

- Registration requires **email verification** (single-use token, 24 h TTL)
  before login; the resend endpoint never reveals whether an address is
  registered. Emails are printed to stdout unless `EMAIL_HOST*` is set.
- Login, registration and verification-resend are **rate limited** (HTTP 429).
- Passwords are validated (length / common / numeric / similarity); reset
  uses signed single-use links; change requires the current password; logout
  is POST-only.
- Sessions: 1 h sliding, HttpOnly, SameSite=Lax, Secure in production.
- CSP + `Permissions-Policy` + `Cross-Origin-Resource-Policy` on every
  non-admin response; HSTS, SSL redirect and Secure cookies when
  `DEBUG=False`; production fails fast without `DJANGO_SECRET_KEY` /
  `DJANGO_ALLOWED_HOSTS`.
- All application data is owner-scoped (cross-user access is a 404); status
  changes are POST-only and validated; all output is autoescaped (tested).
- Security events are logged to the `core.security` logger (never passwords
  or tokens) and shipped to `fly logs` in production.

## Layout

```
config/    Django project (settings, urls)
agent/     the whole provider surface + package generation
  llm.py       chat() via stdlib urllib -> Mistral chat completions
  prompts.py   system prompt (one JSON object, no fabrication) + user prompt
  service.py   extract_json, validation/normalization, demo mode
core/      Profile / JobPosting / Application, views, forms, templates
           demo_data.py  fake board postings behind the DEMO_JOBS_ENABLED flag
```

## Deploy on Fly.io

Two apps in the `personal` org, both `shared-cpu-1x` / `256MB` (within the free
tier), region `fra`:

- **`applyagents`** — the web app, https://applyagents.fly.dev (SQLite on a 1 GB
  `data` volume, migrations in `entrypoint.sh`).
- **`applyagent-mail`** — a relay-only Postfix (`deploy/mail/`, config
  `fly.mail.toml`) with **no public IP**: reachable only from the web app over
  Fly's private network at `applyagent-mail.internal:25`, so it cannot be
  abused as an open relay. Outbound mail is delivered directly to recipient
  MXes on port 25; MX lookups go through a tiny stdlib DNS-over-HTTPS bridge
  (`deploy/mail/dnsbridge.py`) because Fly's built-in resolver does not return
  MX records and public DNS is blocked from Fly machines.

```bash
fly deploy --local-only --yes -a applyagents                 # web app
fly deploy --config fly.mail.toml --local-only --yes         # mail relay
fly logs -a applyagent-mail                                  # see status=sent lines
```

The web app is pointed at the relay via non-secret env in `fly.toml`
(`EMAIL_HOST=applyagent-mail.internal`, port 25, no TLS/auth inside the 6PN).
Without `EMAIL_HOST`, emails fall back to the console backend (printed to
`fly logs`) — useful for local dev and tests.

**Deliverability caveat:** the sender IP is Fly's shared egress and the
`From` domain is `applyagents.fly.dev` (no SPF/DKIM possible on a fly.dev
subdomain), so first mails to Gmail/Outlook/Tuta may land in spam. For
production-grade delivery, attach a custom domain to the Fly app and publish
SPF/DKIM/DMARC for it (and set `DEFAULT_FROM_EMAIL` accordingly), or relay via
a provider's submission port instead.

`Dockerfile`, `.dockerignore`, `fly.toml` and `fly.mail.toml` are committed.
The web image keeps the runtime dependency Django-only (gunicorn is installed
into the venv at image build time). SQLite lives on a Fly volume
(`APPLYAGENT_DB=/data/db.sqlite3`).

```bash
fly auth login                                              # browser sign-up/login
fly apps create applyagents                                 # app name; update `app` in fly.toml if taken
fly volumes create data --size 1 --region fra -a applyagents   # persistent SQLite
fly secrets set -a applyagents DJANGO_SECRET_KEY="$(openssl rand -hex 32)"
fly secrets set -a applyagents MISTRAL_API_KEY=...         # optional; without it the app runs in demo mode
fly deploy --local-only -a applyagents                      # web app (entrypoint.sh migrates, then gunicorn)
fly deploy --config fly.mail.toml --local-only              # mail relay
```

The app answers on `https://applyagents.fly.dev` (HTTPS forced by Fly;
`DJANGO_CSRF_TRUSTED_ORIGINS` / `SECURE_PROXY_SSL_HEADER` are wired in
`config/settings.py`). Useful env knobs on any host: `DEBUG`,
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `APPLYAGENT_DB`,
`MISTRAL_API_KEY`, `MISTRAL_MODEL`, `MISTRAL_TIMEOUT`, `DJANGO_SECRET_KEY`,
`EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_USE_TLS`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`
/`DEFAULT_FROM_EMAIL`, and the `RATE_LIMIT_*` knobs.

## v1 roadmap (recruiter side)

- Recruiter accounts and a recruiter-side dashboard of incoming
  applications (the other half of the AI-augmented LinkedIn).
- One-click submission of a reviewed package to the source posting.
- Pipeline views per application (draft → ready → submitted → interview →
  offer / rejected) with reminders and follow-up drafts.
- Richer matching: embeddings-based match score, per-requirement coverage.
- Multi-provider LLM layer (swap `agent/llm.py` only).
