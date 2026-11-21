"""Cross-user ownership rules: a second user must get 404 on everything.

Regression trap: these must fail (200/302 instead of 404) when the views do
not filter by request.user, and pass once they do.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Application, JobPosting, Profile

PASSWORD = "Str0ng!Pass99"


@override_settings(MISTRAL_API_KEY=None)
class OwnershipTests(TestCase):
    def setUp(self) -> None:
        self.alice = User.objects.create_user(username="alice", password=PASSWORD)
        self.bob = User.objects.create_user(username="bob", password=PASSWORD)
        Profile.objects.create(user=self.alice, headline="Alice", skills="Python")
        job = JobPosting.objects.create(
            owner=self.alice,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs with Django.",
        )
        self.app = Application.objects.create(
            job=job,
            user=self.alice,
            tailored_summary="DEMO OUTPUT: summary",
            cover_letter="DEMO OUTPUT: letter",
            agent_mode="demo",
            agent_model="demo",
        )
        self.client.force_login(self.bob)

    def detail_url(self) -> str:
        return reverse("core:application_detail", args=[self.app.pk])

    def test_detail_returns_404_for_other_user(self) -> None:
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 404)

    def test_edit_get_returns_404_for_other_user(self) -> None:
        response = self.client.get(reverse("core:application_edit", args=[self.app.pk]))
        self.assertEqual(response.status_code, 404)

    def test_edit_post_returns_404_and_does_not_modify(self) -> None:
        response = self.client.post(
            reverse("core:application_edit", args=[self.app.pk]),
            {"tailored_summary": "hijacked", "cover_letter": "hijacked"},
        )
        self.assertEqual(response.status_code, 404)
        self.app.refresh_from_db()
        self.assertEqual(self.app.tailored_summary, "DEMO OUTPUT: summary")

    def test_regenerate_post_returns_404(self) -> None:
        response = self.client.post(
            reverse("core:application_regenerate", args=[self.app.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 404)

    def test_status_post_returns_404_and_does_not_change_status(self) -> None:
        response = self.client.post(
            reverse("core:application_status", args=[self.app.pk]), {"status": "ready"}
        )
        self.assertEqual(response.status_code, 404)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.DRAFT)

    def test_delete_get_returns_404_for_other_user(self) -> None:
        response = self.client.get(reverse("core:application_delete", args=[self.app.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_post_returns_404_and_keeps_everything(self) -> None:
        response = self.client.post(reverse("core:application_delete", args=[self.app.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Application.objects.filter(pk=self.app.pk).exists())
        self.assertTrue(JobPosting.objects.filter(pk=self.app.job.pk).exists())
