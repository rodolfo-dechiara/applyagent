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

CI (`.github/workflows/ci.yml`) runs lint, types and tests on pushes and
PRs to `main` via the official `astral-sh/setup-uv` action.

## Layout

```
config/    Django project (settings, urls)
agent/     the whole provider surface + package generation
  llm.py       chat() via stdlib urllib -> Mistral chat completions
  prompts.py   system prompt (one JSON object, no fabrication) + user prompt
  service.py   extract_json, validation/normalization, demo mode
core/      Profile / JobPosting / Application, views, forms, templates
```

## v1 roadmap (recruiter side)

- Recruiter accounts and a recruiter-side dashboard of incoming
  applications (the other half of the AI-augmented LinkedIn).
- One-click submission of a reviewed package to the source posting.
- Pipeline views per application (draft → ready → submitted → interview →
  offer / rejected) with reminders and follow-up drafts.
- Richer matching: embeddings-based match score, per-requirement coverage.
- Multi-provider LLM layer (swap `agent/llm.py` only).
