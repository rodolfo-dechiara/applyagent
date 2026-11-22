"""AI match score on the board (authenticated only) with skeleton placeholders,
and the detailed AI insight + shining Apply button on the posting detail page.
Red-first."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import JobPosting, Profile
from core.tests.utils import PASSWORD


@override_settings(MISTRAL_API_KEY=None)
class MatchScoreUiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = User.objects.create_user(username="rec", password=PASSWORD)
        self.candidate = User.objects.create_user(username="cand", password=PASSWORD)
        Profile.objects.create(
            user=self.candidate, headline="Backend engineer", skills="Python, Django, SQL"
        )
        self.public_job = JobPosting.objects.create(
            owner=self.owner,
            title="Django developer",
            company="Acme",
            description="Build APIs with Django, Python and SQL.",
            is_public=True,
        )
        self.private_job = JobPosting.objects.create(
            owner=self.owner, title="Secret role", company="Hidden", description="d"
        )

    # --- board list ---
    def test_board_anonymous_sees_login_note_not_score(self) -> None:
        response = self.client.get(reverse("core:job_board"))
        self.assertContains(response, "Log in to see your AI match score")
        self.assertNotContains(response, 'class="skeleton')
        self.assertNotContains(response, reverse("core:job_score", args=[self.public_job.uid]))

    def test_board_authenticated_sees_skeleton_loading_score(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_board"))
        score_url = reverse("core:job_score", args=[self.public_job.uid])
        self.assertContains(response, "skeleton")
        self.assertContains(response, f'hx-get="{score_url}"')

    # --- score endpoint ---
    def test_score_endpoint_requires_login(self) -> None:
        response = self.client.get(reverse("core:job_score", args=[self.public_job.uid]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_score_endpoint_returns_badge_partial(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_score", args=[self.public_job.uid]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/_score_badge.html")
        self.assertContains(response, "match")
        self.assertContains(response, "/100")
        # heuristic: python, django, sql all appear -> 40 + 3*10 = 70
        self.assertContains(response, "70")

    def test_score_endpoint_404_for_other_users_private_posting(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_score", args=[self.private_job.uid]))
        self.assertEqual(response.status_code, 404)

    # --- detail insight ---
    def test_detail_anonymous_has_no_insight_or_apply(self) -> None:
        response = self.client.get(reverse("core:job_board_detail", args=[self.public_job.uid]))
        self.assertNotContains(response, 'class="skeleton')
        self.assertNotContains(response, reverse("core:job_insight", args=[self.public_job.uid]))
        self.assertNotContains(
            response, reverse("core:job_board_apply", args=[self.public_job.uid])
        )
        self.assertContains(response, reverse("login"))

    def test_detail_authenticated_has_insight_skeleton(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_board_detail", args=[self.public_job.uid]))
        insight_url = reverse("core:job_insight", args=[self.public_job.uid])
        self.assertContains(response, "skeleton")
        self.assertContains(response, f'hx-get="{insight_url}"')

    def test_insight_endpoint_returns_detail_and_shining_apply(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_insight", args=[self.public_job.uid]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/_insight.html")
        self.assertContains(response, "DEMO OUTPUT")  # demo-mode reasons/red flags
        self.assertContains(response, "match")
        self.assertContains(response, "Apply")
        self.assertContains(response, "✨")
        self.assertContains(response, 'class="shine"')
        self.assertContains(
            response, f'action="{reverse("core:job_board_apply", args=[self.public_job.uid])}"'
        )

    def test_insight_endpoint_404_for_other_users_private_posting(self) -> None:
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("core:job_insight", args=[self.private_job.uid]))
        self.assertEqual(response.status_code, 404)

    def test_insight_endpoint_requires_login(self) -> None:
        response = self.client.get(reverse("core:job_insight", args=[self.public_job.uid]))
        self.assertEqual(response.status_code, 302)
