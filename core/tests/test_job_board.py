"""Tests for the public job board and the demo-postings feature flag.

Written red before the behavior exists (TDD): each class below failed before
its implementation was added.
"""

from django.contrib.auth.models import User
from django.test import TestCase

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
