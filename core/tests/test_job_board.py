"""Tests for the public job board and the demo-postings feature flag.

Written red before the behavior exists (TDD): each class below failed before
its implementation was added.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.models import JobPosting
from core.tests.utils import PASSWORD


class JobPostingVisibilityTests(TestCase):
    """Cycle 1: a posting is private by default and can be made public."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)

    def test_is_public_defaults_to_false(self) -> None:
        job = JobPosting.objects.create(
            owner=self.user,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs.",
        )
        self.assertFalse(job.is_public)

    def test_can_be_marked_public(self) -> None:
        job = JobPosting.objects.create(
            owner=self.user,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs.",
            is_public=True,
        )
        self.assertTrue(JobPosting.objects.get(pk=job.pk).is_public)


class DemoJobsFlagTests(TestCase):
    """Cycle 2a: the demo-postings feature flag is off unless explicitly enabled."""

    def test_flag_defaults_to_off(self) -> None:
        self.assertFalse(settings.DEMO_JOBS_ENABLED)


class EnsureDemoJobsTests(TestCase):
    """Cycle 2b: ensure_demo_jobs() seeds clearly-marked public fake postings
    only when the flag is on, and is idempotent."""

    def test_noop_when_flag_off(self) -> None:
        from core.demo_data import ensure_demo_jobs

        created = ensure_demo_jobs()
        self.assertEqual(created, 0)
        self.assertEqual(JobPosting.objects.count(), 0)
        self.assertFalse(User.objects.filter(username="demo-board").exists())

    @override_settings(DEMO_JOBS_ENABLED=True)
    def test_seeds_public_marked_demo_postings_when_flag_on(self) -> None:
        from core.demo_data import DEMO_POSTINGS, ensure_demo_jobs

        created = ensure_demo_jobs()
        self.assertEqual(created, len(DEMO_POSTINGS))
        self.assertGreater(created, 0)
        postings = JobPosting.objects.all()
        self.assertTrue(all(p.is_public for p in postings))
        self.assertTrue(all("DEMO POSTING" in p.description for p in postings))
        owner = User.objects.get(username="demo-board")
        self.assertFalse(owner.has_usable_password())
        self.assertTrue(all(p.owner == owner for p in postings))

    @override_settings(DEMO_JOBS_ENABLED=True)
    def test_idempotent_second_call_creates_nothing(self) -> None:
        from core.demo_data import ensure_demo_jobs

        ensure_demo_jobs()
        count = JobPosting.objects.count()
        self.assertEqual(ensure_demo_jobs(), 0)
        self.assertEqual(JobPosting.objects.count(), count)
