"""Input validation & output encoding (ASVS V5, OWASP A03/A05).

Regression tests: everything user-supplied is escaped on render (Django
autoescaping), source URLs are http/https only, free text is length-capped,
CSRF is enforced, and every app page requires login.
"""

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import Application, JobPosting, Profile
from core.tests.utils import PASSWORD

XSS = "<script>alert(1)</script>"
XSS_IMG = "<img src=x onerror=alert(1)>"


@override_settings(MISTRAL_API_KEY=None)
class OutputEncodingTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.client.force_login(self.user)
        self.job = JobPosting.objects.create(
            owner=self.user, title=XSS, company=XSS, description=XSS
        )
        self.app = Application.objects.create(
            job=self.job,
            user=self.user,
            tailored_summary=XSS,
            cover_letter=XSS_IMG,
            screening_answers=[{"question": XSS, "answer": XSS}],
            match_reasons=[XSS],
            red_flags=[XSS],
            agent_mode="demo",
        )

    def assert_escaped(self, response) -> None:
        self.assertNotContains(response, XSS)
        self.assertNotContains(response, XSS_IMG)
        self.assertContains(response, "&lt;script&gt;")
        self.assertContains(response, "&lt;img")

    def test_application_detail_escapes_all_user_content(self) -> None:
        response = self.client.get(reverse("core:application_detail", args=[self.app.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_escaped(response)

    def test_htmx_partial_escapes_all_user_content(self) -> None:
        # Render the swapped partial directly (a real regenerate would replace
        # the stored package with fresh demo output).
        from django.template.loader import render_to_string

        html = render_to_string("core/_package.html", {"application": self.app})
        self.assertNotIn(XSS, html)
        self.assertNotIn(XSS_IMG, html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)

    def test_dashboard_escapes_job_title(self) -> None:
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, XSS)
        self.assertContains(response, "&lt;script&gt;")

    def test_profile_form_escapes_headline(self) -> None:
        Profile.objects.create(user=self.user, headline=XSS)
        response = self.client.get(reverse("core:profile"))
        self.assertNotContains(response, XSS)
        self.assertContains(response, "&lt;script&gt;")

    def test_edit_saved_payload_is_escaped_on_detail(self) -> None:
        self.client.post(
            reverse("core:application_edit", args=[self.app.pk]),
            {"tailored_summary": XSS, "cover_letter": XSS_IMG},
        )
        response = self.client.get(reverse("core:application_detail", args=[self.app.pk]))
        self.assert_escaped(response)


@override_settings(MISTRAL_API_KEY=None)
class InputValidationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.client.force_login(self.user)

    def job_payload(self, **overrides):
        payload = {
            "title": "Django developer",
            "company": "Acme",
            "description": "Build APIs.",
            "source_url": "",
        }
        payload.update(overrides)
        return payload

    def test_javascript_scheme_source_url_is_rejected(self) -> None:
        response = self.client.post(
            reverse("core:job_new"),
            self.job_payload(source_url="javascript:alert(1)"),
        )
        self.assertEqual(response.status_code, 200)  # form error
        self.assertFalse(JobPosting.objects.exists())

    def test_non_http_scheme_source_url_is_rejected(self) -> None:
        response = self.client.post(
            reverse("core:job_new"), self.job_payload(source_url="ftp://example.com/x")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(JobPosting.objects.exists())

    def test_https_source_url_is_accepted(self) -> None:
        response = self.client.post(
            reverse("core:job_new"),
            self.job_payload(source_url="https://jobs.example.com/1"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(JobPosting.objects.exists())

    def test_oversized_description_is_rejected(self) -> None:
        response = self.client.post(
            reverse("core:job_new"), self.job_payload(description="x" * 50_001)
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(JobPosting.objects.exists())

    def test_oversized_cv_text_is_rejected(self) -> None:
        response = self.client.post(
            reverse("core:profile"),
            {
                "headline": "ok",
                "skills": "",
                "experience": "",
                "education": "",
                "links": "",
                "cv_text": "x" * 50_001,
            },
        )
        self.assertEqual(response.status_code, 200)
        # The view may create an empty profile row, but the oversized value
        # must not be saved.
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.cv_text, "")

    def test_oversized_cover_letter_edit_is_rejected(self) -> None:
        job = JobPosting.objects.create(owner=self.user, title="t", description="d")
        app = Application.objects.create(job=job, user=self.user)
        response = self.client.post(
            reverse("core:application_edit", args=[app.pk]),
            {"tailored_summary": "ok", "cover_letter": "x" * 20_001},
        )
        self.assertEqual(response.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.cover_letter, "")


class CsrfAndAnonymousTests(TestCase):
    def test_post_without_csrf_token_is_403(self) -> None:
        user = User.objects.create_user(username="alice", password=PASSWORD)
        job = JobPosting.objects.create(owner=user, title="t", description="d")
        app = Application.objects.create(job=job, user=user)
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        response = client.post(
            reverse("core:application_status", args=[app.pk]), {"status": "ready"}
        )
        self.assertEqual(response.status_code, 403)

    def test_every_app_page_requires_login(self) -> None:
        user = User.objects.create_user(username="alice", password=PASSWORD)
        job = JobPosting.objects.create(owner=user, title="t", description="d")
        app = Application.objects.create(job=job, user=user)
        urls = [
            reverse("core:dashboard"),
            reverse("core:profile"),
            reverse("core:job_new"),
            reverse("core:application_detail", args=[app.pk]),
            reverse("core:application_edit", args=[app.pk]),
            reverse("core:application_delete", args=[app.pk]),
            reverse("core:application_regenerate", args=[app.pk]),
            reverse("core:application_status", args=[app.pk]),
        ]
        client = Client()
        for url in urls:
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])
