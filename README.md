# ApplyAgent v0

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

## Development

```bash
uv run python manage.py test          # full suite (demo mode)
uv run ruff check .                   # lint
uv run ruff format --check .          # format check
uv run pyrefly check                  # type check
uvx pre-commit run --all-files        # hooks (ruff, ruff-format, pyrefly)
```

CI (`.github/workflows/ci.yml`) runs lint, types, tests and a `pip-audit`
dependency scan on pushes and PRs to `main` via the official
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
```

## Deploy on Fly.io

`Dockerfile`, `.dockerignore` and `fly.toml` are committed. The image keeps
the runtime dependency Django-only (gunicorn is installed into the venv at
image build time). SQLite lives on a Fly volume (`APPLYAGENT_DB=/data/db.sqlite3`).

```bash
fly auth login                                        # browser sign-up/login
fly apps create applyagent                            # if the name is taken, pick another
                                                      # and update `app` + the DJANGO_* URLs in fly.toml
fly volumes create data --size 1 --region fra         # persistent SQLite
fly secrets set DJANGO_SECRET_KEY="$(openssl rand -hex 32)"
fly secrets set MISTRAL_API_KEY=...                   # optional; without it the app runs in demo mode
fly deploy                                            # builds the image; entrypoint.sh runs migrate, then gunicorn
```

The app then answers on `https://applyagent.fly.dev` (HTTPS is forced by Fly;
`DJANGO_CSRF_TRUSTED_ORIGINS` / `SECURE_PROXY_SSL_HEADER` are wired in
`config/settings.py` for that). Useful env knobs on any host: `DEBUG`,
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `APPLYAGENT_DB`,
`MISTRAL_API_KEY`, `MISTRAL_MODEL`, `MISTRAL_TIMEOUT`, `DJANGO_SECRET_KEY`.

## v1 roadmap (recruiter side)

- Recruiter accounts and a recruiter-side dashboard of incoming
  applications (the other half of the AI-augmented LinkedIn).
- One-click submission of a reviewed package to the source posting.
- Pipeline views per application (draft → ready → submitted → interview →
  offer / rejected) with reminders and follow-up drafts.
- Richer matching: embeddings-based match score, per-requirement coverage.
- Multi-provider LLM layer (swap `agent/llm.py` only).
