"""Candidate/recruiter roles. Users pick a role at registration; recruiters
publish job offers (public postings, no application generated), candidates
paste postings and get packages. Red-first."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Account, Application, JobPosting
from core.tests.utils import PASSWORD, register_and_verify


@override_settings(MISTRAL_API_KEY=None)
class RoleTests(TestCase):
    def setUp(self) -> None:
        cache.clear()  # register is rate-limited per IP; don't share the budget

    def test_register_form_offers_candidate_and_recruiter_roles(self) -> None:
        response = self.client.get(reverse("register"))
        self.assertContains(response, "candidate")
        self.assertContains(response, "recruiter")
        self.assertContains(response, 'name="role"')

    def test_registering_as_recruiter_creates_recruiter_account(self) -> None:
        response = self.client.post(
            reverse("register"),
            {
                "username": "rec1",
                "email": "rec1@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "role": "recruiter",
            },
        )
        self.assertEqual(response.status_code, 302)
        account = Account.objects.get(user__username="rec1")
        self.assertEqual(account.role, Account.Role.RECRUITER)

    def test_default_role_is_candidate(self) -> None:
        register_and_verify(self.client, username="cand1")
        account = Account.objects.get(user__username="cand1")
        self.assertEqual(account.role, Account.Role.CANDIDATE)

    def test_existing_users_without_account_row_default_to_candidate(self) -> None:
        user = User.objects.create_user(username="legacy", password=PASSWORD)
        account, created = Account.objects.get_or_create(user=user)
        self.assertTrue(created)
        self.assertEqual(account.role, Account.Role.CANDIDATE)

    def test_recruiter_pasting_a_job_publishes_offer_without_application(self) -> None:
        register_and_verify(self.client, username="rec2")
        Account.objects.filter(user__username="rec2").update(role=Account.Role.RECRUITER)
        response = self.client.post(
            reverse("core:job_new"),
            {
                "title": "Backend Engineer",
                "company": "Recruiter Co",
                "description": "Build things.",
                "source_url": "https://jobs.example.com/9",
                "is_public": "on",
            },
        )
        job = JobPosting.objects.get(owner__username="rec2")
        self.assertTrue(job.is_public)
        self.assertEqual(Application.objects.count(), 0)  # no self-application
        self.assertRedirects(response, reverse("core:job_board_detail", args=[job.uid]))

    def test_recruiter_offer_is_visible_on_public_board(self) -> None:
        recruiter = User.objects.create_user(username="rec3", password=PASSWORD)
        Account.objects.create(user=recruiter, role=Account.Role.RECRUITER)
        JobPosting.objects.create(
            owner=recruiter, title="Offer Role", company="Co", description="d", is_public=True
        )
        response = self.client.get(reverse("core:job_board"))
        self.assertContains(response, "Offer Role")

    def test_candidate_paste_still_generates_application(self) -> None:
        register_and_verify(self.client, username="cand2")
        response = self.client.post(
            reverse("core:job_new"),
            {
                "title": "Django dev",
                "company": "Acme",
                "description": "Django APIs.",
                "source_url": "",
            },
        )
        self.assertEqual(Application.objects.filter(user__username="cand2").count(), 1)
        self.assertEqual(response.status_code, 302)
