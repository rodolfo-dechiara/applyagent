"""Demo job postings behind the DEMO_JOBS_ENABLED feature flag.

When the flag is on, the public jobs board is seeded with clearly-marked fake
postings ("DEMO POSTING: ...") so a demo never shows an empty board. They are
owned by a dedicated system account that can never log in (unusable password,
inactive). ensure_demo_jobs() is idempotent and safe to call on every board
request; with the flag off it is a no-op.
"""

from django.conf import settings
from django.contrib.auth.models import User

from core.models import JobPosting

DEMO_OWNER_USERNAME = "demo-board"

DEMO_POSTINGS: list[dict[str, str]] = [
    {
        "title": "Senior Backend Engineer (Python/Django)",
        "company": "Example Labs",
        "description": (
            "DEMO POSTING: own our payments API. Requirements: 5+ years Python, "
            "Django, PostgreSQL, async workers. Nice to have: Kubernetes, GraphQL. "
            "Hybrid, Berlin. This is fake demo data shown only when "
            "APPLYAGENT_DEMO_JOBS=true."
        ),
        "source_url": "https://example.com/jobs/senior-backend",
    },
    {
        "title": "Frontend Engineer (Alpine.js/HTMX)",
        "company": "Fictional Studio",
        "description": (
            "DEMO POSTING: build server-rendered UIs with HTMX and Alpine.js — no "
            "JS build step. Tailwind via CDN. You care about accessibility and "
            "mobile-first layouts. Remote, EU. Fake demo data "
            "(APPLYAGENT_DEMO_JOBS=true)."
        ),
        "source_url": "https://example.com/jobs/frontend",
    },
    {
        "title": "Full-stack Engineer",
        "company": "Acme Demo GmbH",
        "description": (
            "DEMO POSTING: Django backend + vanilla JS frontend for a B2B SaaS. "
            "You will ship end to end, write tests first, and review AI-drafted "
            "code. Berlin office. Fake demo data (APPLYAGENT_DEMO_JOBS=true)."
        ),
        "source_url": "https://example.com/jobs/fullstack",
    },
    {
        "title": "Platform Engineer (Fly.io, Postfix, SQLite ops)",
        "company": "Tiny Hosting Co.",
        "description": (
            "DEMO POSTING: run small self-hosted apps on Fly.io: volumes, secrets, "
            "private networking, a relay-only Postfix. You automate deploys and "
            "keep costs near zero. Remote. Fake demo data "
            "(APPLYAGENT_DEMO_JOBS=true)."
        ),
        "source_url": "https://example.com/jobs/platform",
    },
    {
        "title": "Junior Python Developer",
        "company": "Startup Example",
        "description": (
            "DEMO POSTING: learn Django by pairing on a job-application tool. "
            "Mentorship, TDD, code review. No on-call. Remote-first. Fake demo "
            "data (APPLYAGENT_DEMO_JOBS=true)."
        ),
        "source_url": "https://example.com/jobs/junior-python",
    },
]


def ensure_demo_jobs() -> int:
    """Create the demo postings if missing. Returns how many were created.

    No-op (returns 0) unless settings.DEMO_JOBS_ENABLED is true.
    """
    if not settings.DEMO_JOBS_ENABLED:
        return 0
    owner, created = User.objects.get_or_create(
        username=DEMO_OWNER_USERNAME,
        defaults={"email": "demo-board@youre-hired.eu", "is_active": False},
    )
    if created or not owner.password or not owner.has_usable_password():
        owner.set_unusable_password()
        owner.save(update_fields=["password"])
    made = 0
    for data in DEMO_POSTINGS:
        _, was_created = JobPosting.objects.get_or_create(
            owner=owner,
            title=data["title"],
            company=data["company"],
            defaults={
                "description": data["description"],
                "source_url": data["source_url"],
                "is_public": True,
            },
        )
        made += int(was_created)
    return made
