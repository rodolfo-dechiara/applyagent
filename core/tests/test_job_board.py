"""Tests for the public job board and the demo-postings feature flag.

Written red before the behavior exists (TDD): each class below failed before
its implementation was added.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.demo_data import DEMO_POSTINGS
from core.models import Application, JobPosting, Profile
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


class JobBoardListTests(TestCase):
    """Cycle 3: /jobs/ is public, lists only is_public postings, and seeds
    demo postings when the flag is on."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.public_job = JobPosting.objects.create(
            owner=self.user,
            title="Public Platform Role",
            company="Open Corp",
            description="Work on public things.",
            is_public=True,
        )
        self.private_job = JobPosting.objects.create(
            owner=self.user,
            title="Secret Internal Role",
            company="Hidden Inc",
            description="Not for the board.",
        )

    def test_anonymous_can_view_board(self) -> None:
        response = self.client.get(reverse("core:job_board"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/job_board.html")

    def test_only_public_postings_are_listed(self) -> None:
        response = self.client.get(reverse("core:job_board"))
        self.assertContains(response, "Public Platform Role")
        self.assertNotContains(response, "Secret Internal Role")

    def test_empty_state_when_nothing_public(self) -> None:
        JobPosting.objects.all().delete()
        response = self.client.get(reverse("core:job_board"))
        self.assertContains(response, "No public job postings yet")

    @override_settings(DEMO_JOBS_ENABLED=True)
    def test_demo_flag_seeds_board_on_view_and_stays_idempotent(self) -> None:
        response = self.client.get(reverse("core:job_board"))
        self.assertEqual(response.status_code, 200)
        for data in DEMO_POSTINGS:
            self.assertContains(response, data["title"])
        self.assertEqual(
            JobPosting.objects.filter(is_public=True, owner__username="demo-board").count(),
            len(DEMO_POSTINGS),
        )
        self.client.get(reverse("core:job_board"))
        self.assertEqual(
            JobPosting.objects.filter(owner__username="demo-board").count(), len(DEMO_POSTINGS)
        )

    def test_navbar_links_to_board_for_anonymous(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertContains(response, f'href="{reverse("core:job_board")}"')


class JobBoardDetailTests(TestCase):
    """Cycle 4: the board detail page is public for public postings; private
    postings are 404 for anonymous users and for everyone but the owner."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="alice", password=PASSWORD)
        self.other = User.objects.create_user(username="bob", password=PASSWORD)
        self.public_job = JobPosting.objects.create(
            owner=self.owner,
            title="Public Platform Role",
            company="Open Corp",
            description="Full description of the public role.",
            is_public=True,
        )
        self.private_job = JobPosting.objects.create(
            owner=self.owner,
            title="Secret Internal Role",
            company="Hidden Inc",
            description="Confidential description.",
        )

    def test_anonymous_gets_public_detail(self) -> None:
        response = self.client.get(reverse("core:job_board_detail", args=[self.public_job.uid]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/job_board_detail.html")
        self.assertContains(response, "Full description of the public role.")

    def test_anonymous_gets_404_on_private_posting(self) -> None:
        response = self.client.get(reverse("core:job_board_detail", args=[self.private_job.uid]))
        self.assertEqual(response.status_code, 404)

    def test_other_user_gets_404_on_private_posting(self) -> None:
        self.client.force_login(self.other)
        response = self.client.get(reverse("core:job_board_detail", args=[self.private_job.uid]))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_view_own_private_posting(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:job_board_detail", args=[self.private_job.uid]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confidential description.")

    def test_missing_posting_is_404(self) -> None:
        response = self.client.get(reverse("core:job_board_detail", args=["0" * 24 + "0"]))
        self.assertEqual(response.status_code, 404)


@override_settings(MISTRAL_API_KEY=None)
class JobBoardApplyTests(TestCase):
    """Cycle 5: POST /jobs/<pk>/apply/ clones the public posting to the candidate
    and generates their application package (demo mode in tests)."""

    def setUp(self) -> None:
        cache.clear()
        self.owner = User.objects.create_user(username="alice", password=PASSWORD)
        self.candidate = User.objects.create_user(username="bob", password=PASSWORD)
        Profile.objects.create(
            user=self.candidate,
            headline="Backend engineer",
            skills="Python, Django, SQL",
            cv_text="Bob CV body",
        )
        self.public_job = JobPosting.objects.create(
            owner=self.owner,
            title="Public Platform Role",
            company="Open Corp",
            description="Full description of the public role.",
            source_url="https://jobs.example.com/public",
            is_public=True,
        )
        self.private_job = JobPosting.objects.create(
            owner=self.owner,
            title="Secret Internal Role",
            company="Hidden Inc",
            description="Confidential description.",
        )

    def apply_url(self, job: JobPosting) -> str:
        return reverse("core:job_board_apply", args=[job.uid])

    def test_anonymous_post_redirects_to_login_and_creates_nothing(self) -> None:
        postings_before = JobPosting.objects.count()
        response = self.client.post(self.apply_url(self.public_job))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertEqual(Application.objects.count(), 0)
        self.assertEqual(JobPosting.objects.count(), postings_before)

    def test_get_is_405_for_logged_in_user(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(self.apply_url(self.public_job))
        self.assertEqual(response.status_code, 405)

    def test_apply_clones_posting_and_generates_demo_package(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.post(self.apply_url(self.public_job))
        application = Application.objects.get(user=self.candidate)
        self.assertRedirects(response, reverse("core:application_detail", args=[application.uid]))
        # The candidate gets their own private copy of the posting.
        clone = application.job
        self.assertEqual(clone.owner, self.candidate)
        self.assertFalse(clone.is_public)
        self.assertEqual(clone.title, self.public_job.title)
        self.assertEqual(clone.company, self.public_job.company)
        self.assertEqual(clone.source_url, self.public_job.source_url)
        # Demo mode: package is present and clearly marked.
        self.assertEqual(application.agent_mode, "demo")
        self.assertIn("DEMO OUTPUT", application.tailored_summary)
        self.assertIn("DEMO OUTPUT", application.cover_letter)
        # The original public posting is untouched and still public.
        self.public_job.refresh_from_db()
        self.assertTrue(self.public_job.is_public)
        self.assertEqual(self.public_job.owner, self.owner)

    def test_second_apply_does_not_duplicate(self) -> None:
        self.client.force_login(self.candidate)
        self.client.post(self.apply_url(self.public_job))
        response = self.client.post(self.apply_url(self.public_job))
        self.assertEqual(Application.objects.filter(user=self.candidate).count(), 1)
        self.assertEqual(
            JobPosting.objects.filter(owner=self.candidate, title="Public Platform Role").count(),
            1,
        )
        application = Application.objects.get(user=self.candidate)
        self.assertRedirects(response, reverse("core:application_detail", args=[application.uid]))

    def test_other_user_cannot_apply_to_private_posting(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.post(self.apply_url(self.private_job))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Application.objects.count(), 0)

    def test_detail_page_has_insight_skeleton_for_logged_in_user(self) -> None:
        # The Apply form itself arrives via HTMX from the insight endpoint.
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_board_detail", args=[self.public_job.uid]))
        self.assertContains(
            response, f'hx-get="{reverse("core:job_insight", args=[self.public_job.uid])}"'
        )

    def test_detail_page_invites_anonymous_to_log_in(self) -> None:
        response = self.client.get(reverse("core:job_board_detail", args=[self.public_job.uid]))
        self.assertContains(response, reverse("login"))


@override_settings(MISTRAL_API_KEY=None)
class PostingVisibilityFormTests(TestCase):
    """Cycle 6: the paste-a-job form can opt the posting into the public board,
    and the dashboard shows which of your postings are public."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.client.force_login(self.user)

    def paste(self, **extra: str):
        data = {
            "title": "Django developer",
            "company": "Acme Corp",
            "description": "Build APIs with Django.",
            "source_url": "https://jobs.example.com/1",
        }
        data.update(extra)
        return self.client.post(reverse("core:job_new"), data)

    def test_paste_form_has_is_public_checkbox(self) -> None:
        response = self.client.get(reverse("core:job_new"))
        self.assertContains(response, 'name="is_public"')
        self.assertContains(response, "job board")

    def test_pasting_with_checkbox_makes_posting_public_on_board(self) -> None:
        response = self.paste(is_public="on")
        self.assertEqual(response.status_code, 302)
        job = JobPosting.objects.get(owner=self.user)
        self.assertTrue(job.is_public)
        board = self.client.get(reverse("core:job_board"))
        self.assertContains(board, "Django developer")

    def test_pasting_without_checkbox_stays_private(self) -> None:
        self.paste()
        job = JobPosting.objects.get(owner=self.user)
        self.assertFalse(job.is_public)
        board = self.client.get(reverse("core:job_board"))
        self.assertNotContains(board, "Django developer")

    def test_dashboard_marks_public_postings(self) -> None:
        job = JobPosting.objects.create(
            owner=self.user,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs.",
            is_public=True,
        )
        Application.objects.create(job=job, user=self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Public")
