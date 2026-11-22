"""The full loop in one test, in demo mode (no MISTRAL_API_KEY anywhere).

register -> save profile -> paste a job -> application created in demo mode
with a non-empty package -> detail -> HTMX regenerate (200) -> edit saves ->
status updates -> invalid status refused -> delete removes application and
posting.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Application, JobPosting, Profile
from core.tests.utils import register_and_verify

PASSWORD = "Str0ng!Pass99"


@override_settings(MISTRAL_API_KEY=None)
class FullLoopTests(TestCase):
    def test_full_loop_in_demo_mode(self) -> None:
        # 1. Register, then verify the emailed link (logs the user in).
        response = register_and_verify(self.client, username="alice")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="alice", is_active=True).exists())

        # 2. Save the master profile.
        response = self.client.post(
            reverse("core:profile"),
            {
                "headline": "Backend engineer",
                "skills": "Python, Django, SQL",
                "experience": "5 years at Acme",
                "education": "MSc CS",
                "links": "https://example.com/alice",
                "cv_text": "Alice CV body",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.filter(user__username="alice").exists())

        # 3. Paste a job posting: the package is generated immediately (demo).
        response = self.client.post(
            reverse("core:job_new"),
            {
                "title": "Django developer",
                "company": "Acme Corp",
                "description": "Build APIs with Django, Python and SQL.",
                "source_url": "https://jobs.example.com/1",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("review" in m.lower() for m in messages))
        app = Application.objects.get(user__username="alice")
        self.assertEqual(app.agent_mode, "demo")
        self.assertEqual(app.agent_model, "demo")
        self.assertEqual(app.status, Application.Status.DRAFT)
        self.assertTrue(app.tailored_summary.startswith("DEMO OUTPUT:"))
        self.assertTrue(app.cover_letter.startswith("DEMO OUTPUT:"))
        self.assertTrue(app.screening_answers)
        self.assertIsNotNone(app.match_score)
        self.assertIsNotNone(app.generated_at)
        detail_url = reverse("core:application_detail", args=[app.uid])
        self.assertEqual(response.redirect_chain[-1][0], detail_url)

        # 4. Application page renders the package.
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, app.tailored_summary)
        self.assertContains(response, app.cover_letter)

        # 5. HTMX regenerate returns 200 with the swapped partial.
        response = self.client.post(
            reverse("core:application_regenerate", args=[app.uid]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="package"')
        self.assertContains(response, "DEMO OUTPUT")

        # 6. The human review pass: edits save.
        response = self.client.post(
            reverse("core:application_edit", args=[app.uid]),
            {
                "tailored_summary": "My edited summary.",
                "cover_letter": "My edited letter.",
            },
        )
        self.assertEqual(response.status_code, 302)
        app.refresh_from_db()
        self.assertEqual(app.tailored_summary, "My edited summary.")
        self.assertEqual(app.cover_letter, "My edited letter.")

        # 7. Status transitions work.
        response = self.client.post(
            reverse("core:application_status", args=[app.uid]), {"status": "ready"}
        )
        self.assertEqual(response.status_code, 302)
        app.refresh_from_db()
        self.assertEqual(app.status, "ready")

        # 8. An unknown status is refused.
        response = self.client.post(
            reverse("core:application_status", args=[app.uid]),
            {"status": "teleported"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("teleported" in m for m in messages))
        app.refresh_from_db()
        self.assertEqual(app.status, "ready")

        # 9. Delete removes the application and the posting too.
        job_pk = app.job.pk
        response = self.client.post(reverse("core:application_delete", args=[app.uid]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Application.objects.filter(pk=app.pk).exists())
        self.assertFalse(JobPosting.objects.filter(pk=job_pk).exists())
