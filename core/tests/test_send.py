"""Approve-and-send: PDF CV attached to the message emailed to the recruiter
who published the posting. Red-first."""

import re

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Account, Application, JobPosting, Profile
from core.pdf import make_cv_pdf
from core.tests.utils import PASSWORD


class CvPdfTests(TestCase):
    def test_pdf_is_structurally_valid_and_contains_profile_text(self) -> None:
        user = User.objects.create_user(username="cand", password=PASSWORD)
        profile = Profile.objects.create(
            user=user,
            headline="Backend engineer",
            skills="Python, Django",
            experience="5 years at Acme",
            education="MSc CS",
            links="https://example.com/cand",
            cv_text="Built APIs.",
        )
        pdf = make_cv_pdf(profile)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", pdf)
        self.assertIn(b"/Type /Page", pdf)
        self.assertIn(b"Backend engineer", pdf)
        self.assertIn(b"5 years at Acme", pdf)
        # xref offset must point at the xref table
        match = re.search(rb"startxref\s+(\d+)", pdf)
        assert match is not None
        startxref = int(match.group(1))
        self.assertTrue(pdf[startxref:].startswith(b"xref"))

    def test_pdf_escapes_special_chars(self) -> None:
        user = User.objects.create_user(username="cand2", password=PASSWORD)
        profile = Profile.objects.create(user=user, headline="A (tricky) \\ headline")
        pdf = make_cv_pdf(profile)
        self.assertIn(b"A \\(tricky\\) \\\\ headline", pdf)


@override_settings(MISTRAL_API_KEY=None)
class SendToRecruiterTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.recruiter = User.objects.create_user(
            username="rec", email="recruiter@example.com", password=PASSWORD
        )
        Account.objects.create(user=self.recruiter, role=Account.Role.RECRUITER)
        self.candidate = User.objects.create_user(
            username="cand", email="cand@example.com", password=PASSWORD
        )
        Account.objects.create(user=self.candidate, role=Account.Role.CANDIDATE)
        Profile.objects.create(
            user=self.candidate, headline="Backend engineer", skills="Python, Django"
        )
        self.offer = JobPosting.objects.create(
            owner=self.recruiter,
            title="Django developer",
            company="Recruiter Co",
            description="Build APIs.",
            is_public=True,
        )
        self.job = JobPosting.objects.create(
            owner=self.candidate,
            title="Django developer",
            company="Recruiter Co",
            description="Build APIs.",
        )
        self.application = Application.objects.create(
            job=self.job,
            user=self.candidate,
            source_posting=self.offer,
            tailored_summary="DEMO OUTPUT: my summary",
            cover_letter="DEMO OUTPUT: my letter",
            match_score=80,
            match_reasons=["DEMO OUTPUT: strong skills"],
            red_flags=["DEMO OUTPUT: no portfolio"],
            agent_mode="demo",
            agent_model="demo",
        )
        self.client.force_login(self.candidate)

    def send_url(self) -> str:
        return reverse("core:application_send", args=[self.application.uid])

    def detail_url(self) -> str:
        return reverse("core:application_detail", args=[self.application.uid])

    def test_send_emails_recruiter_with_pdf_cv_and_presentation(self) -> None:
        response = self.client.post(self.send_url())
        self.assertRedirects(response, self.detail_url())
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["recruiter@example.com"])
        self.assertIn("Django developer", message.subject)
        # presentation (summary + cover letter) is in the message body
        self.assertIn("DEMO OUTPUT: my summary", message.body)
        self.assertIn("DEMO OUTPUT: my letter", message.body)
        self.assertIn("80/100", message.body)
        # CV attached as PDF
        self.assertEqual(len(message.attachments), 1)
        filename, content, content_type = message.attachments[0]
        self.assertEqual(filename, "CV_cand.pdf")
        self.assertEqual(content_type, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertIn(b"Backend engineer", content)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.SUBMITTED)

    def test_send_twice_is_refused(self) -> None:
        self.client.post(self.send_url())
        response = self.client.post(self.send_url())
        self.assertRedirects(response, self.detail_url())
        self.assertEqual(len(mail.outbox), 1)  # no second email
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("twice" in m for m in messages))

    def test_send_get_is_405(self) -> None:
        response = self.client.get(self.send_url())
        self.assertEqual(response.status_code, 405)

    def test_send_requires_login(self) -> None:
        self.client.logout()
        response = self.client.post(self.send_url())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_other_user_gets_404_on_send(self) -> None:
        other = User.objects.create_user(username="other", password=PASSWORD)
        self.client.force_login(other)
        response = self.client.post(self.send_url())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_candidate_owned_posting_marks_submitted_without_email(self) -> None:
        # posting pasted by a candidate (not a recruiter): nothing to send to
        candidate_owner_posting = JobPosting.objects.create(
            owner=self.candidate, title="Self practice", company="Me", description="d"
        )
        app = Application.objects.create(job=candidate_owner_posting, user=self.candidate)
        response = self.client.post(reverse("core:application_send", args=[app.uid]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.SUBMITTED)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="127.0.0.1",
        EMAIL_PORT=1,
        EMAIL_USE_TLS=False,
    )
    def test_email_failure_does_not_mark_submitted(self) -> None:
        response = self.client.post(self.send_url())
        self.assertRedirects(response, self.detail_url())
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.DRAFT)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("could not" in m.lower() or "failed" in m.lower() for m in messages))

    def test_detail_page_shows_approve_send_button_until_submitted(self) -> None:
        response = self.client.get(self.detail_url())
        self.assertContains(response, reverse("core:application_send", args=[self.application.uid]))
        self.assertContains(response, "Approve")
        self.client.post(self.send_url())
        response = self.client.get(self.detail_url())
        self.assertNotContains(
            response, reverse("core:application_send", args=[self.application.uid])
        )
