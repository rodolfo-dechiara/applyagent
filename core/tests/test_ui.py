"""UI modernization locks: the base template loads Inter via Google Fonts,
uses gradient styling, and the CSP allows the font hosts."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.tests.utils import PASSWORD, register_and_verify


class ModernUiTests(TestCase):
    def test_brand_is_youre_hired_everywhere(self) -> None:
        """Rebrand lock: navbar logo and page title show the youre-hired.eu brand."""
        response = self.client.get(reverse("login"))
        html = response.content.decode()
        self.assertIn("You're Hired", html)  # navbar logo
        self.assertIn("<title>Log in — You're Hired</title>", html)
        self.assertNotIn("ApplyAgent", html)

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

    def test_form_controls_are_full_width_with_visible_focus_outline(self) -> None:
        # Global CSS in base.html styles ALL inputs (Django's auth forms don't
        # carry Tailwind classes): full width + a visible indigo focus outline.
        response = self.client.get(reverse("login"))
        html = response.content.decode()
        self.assertIn('input[type="password"]', html)
        self.assertIn("width: 100%", html)
        self.assertIn("outline:", html)
        self.assertIn(":focus", html)

    def test_navbar_has_title_left_and_actions_right(self) -> None:
        response = self.client.get(reverse("login"))
        html = response.content.decode()
        self.assertIn("justify-between", html)  # logo left, log in/register right
        # The gradient logo link comes before the auth action links in the navbar.
        logo_marker = "bg-clip-text text-lg font-extrabold"
        login_link = f'href="{reverse("login")}"'
        register_link = f'href="{reverse("register")}"'
        self.assertLess(html.index(logo_marker), html.index(login_link))
        self.assertLess(html.index(login_link), html.index(register_link))

    def test_mobile_navigation_hamburger_present(self) -> None:
        response = self.client.get(reverse("login"))
        html = response.content.decode()
        # Alpine-driven mobile menu, hidden on md+ screens, desktop links hidden below md.
        self.assertIn('x-data="{ open: false }"', html)
        self.assertIn('@click="open = !open"', html)
        self.assertIn("x-cloak", html)
        self.assertIn("md:hidden", html)
        self.assertIn("md:flex", html)
        self.assertIn("[x-cloak]", html)  # CSS guard so the panel never flashes

    def test_headings_are_mobile_first(self) -> None:
        register_and_verify(self.client, username="alice")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "text-2xl font-extrabold sm:text-3xl")

    def test_application_detail_uses_gradient_title(self) -> None:
        user = User.objects.create_user(username="alice", password=PASSWORD)
        from core.models import Application, JobPosting

        job = JobPosting.objects.create(owner=user, title="Django developer", description="d")
        app = Application.objects.create(job=job, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse("core:application_detail", args=[app.uid]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bg-gradient-to-r")
        self.assertContains(response, 'id="package"')
