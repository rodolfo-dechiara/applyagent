"""UI modernization locks: the base template loads Inter via Google Fonts,
uses gradient styling, and the CSP allows the font hosts."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.tests.utils import PASSWORD, register_and_verify


class ModernUiTests(TestCase):
    def test_login_page_loads_inter_font_and_gradients(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("fonts.googleapis.com", html)  # Inter stylesheet
        self.assertIn("Inter", html)  # font-family in the inline style block
        self.assertIn("bg-gradient-to-r", html)  # gradient branding/buttons
        self.assertIn("backdrop-blur", html)  # glassy navbar

    def test_csp_allows_font_hosts(self) -> None:
        response = self.client.get(reverse("login"))
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("https://fonts.googleapis.com", csp)
        self.assertIn("https://fonts.gstatic.com", csp)

    def test_dashboard_uses_gradient_heading(self) -> None:
        register_and_verify(self.client, username="alice")
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bg-gradient-to-r")

    def test_application_detail_uses_gradient_title(self) -> None:
        user = User.objects.create_user(username="alice", password=PASSWORD)
        from core.models import Application, JobPosting

        job = JobPosting.objects.create(owner=user, title="Django developer", description="d")
        app = Application.objects.create(job=job, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse("core:application_detail", args=[app.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bg-gradient-to-r")
        self.assertContains(response, 'id="package"')
