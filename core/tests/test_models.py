"""Tests for the core data model: Profile, JobPosting, Application."""

import unittest

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from core.models import Application, JobPosting, Profile


class ModelTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password="pw12345!")
        self.other = User.objects.create_user(username="bob", password="pw12345!")

    def make_profile(self, user: User | None = None) -> Profile:
        return Profile.objects.create(
            user=user or self.user,
            headline="Backend engineer",
            skills="Python, Django, SQL",
            experience="5 years at Acme",
            education="MSc Computer Science",
            links="https://example.com/alice",
            cv_text="Alice CV text",
        )

    def make_job(self, owner: User | None = None) -> JobPosting:
        return JobPosting.objects.create(
            owner=owner or self.user,
            title="Django developer",
            company="Acme",
            description="We need a Django developer. Python, SQL, APIs.",
            source_url="https://jobs.example.com/123",
        )


class ProfileTests(ModelTestCase):
    def test_one_profile_per_user(self) -> None:
        self.make_profile()
        with self.assertRaises(IntegrityError):
            Profile.objects.create(user=self.user, headline="duplicate")

    def test_profile_reachable_from_user(self) -> None:
        profile = self.make_profile()
        self.assertEqual(Profile.objects.get(user=self.user), profile)

    def test_profile_fields_roundtrip(self) -> None:
        profile = self.make_profile()
        fetched = Profile.objects.get(pk=profile.pk)
        self.assertEqual(fetched.headline, "Backend engineer")
        self.assertEqual(fetched.skills, "Python, Django, SQL")
        self.assertEqual(fetched.experience, "5 years at Acme")
        self.assertEqual(fetched.education, "MSc Computer Science")
        self.assertEqual(fetched.links, "https://example.com/alice")
        self.assertEqual(fetched.cv_text, "Alice CV text")


class JobPostingTests(ModelTestCase):
    def test_job_belongs_to_owner(self) -> None:
        job = self.make_job()
        self.assertIn(job, JobPosting.objects.filter(owner=self.user))
        self.assertNotIn(job, JobPosting.objects.filter(owner=self.other))

    def test_job_fields_roundtrip(self) -> None:
        job = self.make_job()
        fetched = JobPosting.objects.get(pk=job.pk)
        self.assertEqual(fetched.title, "Django developer")
        self.assertEqual(fetched.company, "Acme")
        self.assertEqual(fetched.description, "We need a Django developer. Python, SQL, APIs.")
        self.assertEqual(fetched.source_url, "https://jobs.example.com/123")


class ApplicationTests(ModelTestCase):
    def test_status_choices(self) -> None:
        values = {choice for choice, _label in Application.Status.choices}
        self.assertEqual(values, {"draft", "ready", "submitted", "interview", "offer", "rejected"})

    def test_default_status_is_draft(self) -> None:
        job = self.make_job()
        app = Application.objects.create(job=job, user=self.user)
        self.assertEqual(app.status, Application.Status.DRAFT)

    def test_one_application_per_job(self) -> None:
        job = self.make_job()
        Application.objects.create(job=job, user=self.user)
        with self.assertRaises(IntegrityError):
            Application.objects.create(job=job, user=self.user)

    def test_package_fields_default_empty_and_score_nullable(self) -> None:
        job = self.make_job()
        app = Application.objects.create(job=job, user=self.user)
        self.assertEqual(app.tailored_summary, "")
        self.assertEqual(app.cover_letter, "")
        self.assertEqual(app.screening_answers, [])
        self.assertEqual(app.match_reasons, [])
        self.assertEqual(app.red_flags, [])
        self.assertIsNone(app.match_score)

    def test_deleting_job_cascades_to_application(self) -> None:
        job = self.make_job()
        app = Application.objects.create(job=job, user=self.user)
        job.delete()
        self.assertFalse(Application.objects.filter(pk=app.pk).exists())

    def test_application_listed_under_user(self) -> None:
        job = self.make_job()
        app = Application.objects.create(job=job, user=self.user)
        self.assertIn(app, Application.objects.filter(user=self.user))


if __name__ == "__main__":
    unittest.main()
