"""Marketing landing page at / (public), dashboard moved to /dashboard/.

Written red before the landing view existed.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.demo_data import DEMO_POSTINGS
from core.models import JobPosting
from core.tests.utils import PASSWORD


class LandingPageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)

    def make_posting(self, title: str, public: bool = True) -> JobPosting:
        return JobPosting.objects.create(
            owner=self.user,
            title=title,
            company="Acme",
            description=f"About {title}.",
            is_public=public,
        )

    def test_root_is_public_landing_for_anonymous(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/landing.html")

    def test_landing_shows_brand_and_ctas(self) -> None:
        response = self.client.get("/")
        self.assertContains(response, "You're Hired")
        self.assertContains(response, f'href="{reverse("core:job_board")}"')  # jobs CTA
        self.assertContains(response, f'href="{reverse("register")}"')  # register CTA

    def test_landing_navbar_has_jobs_link_for_anonymous(self) -> None:
        response = self.client.get("/")
        html = response.content.decode()
        self.assertIn(f'href="{reverse("core:job_board")}"', html)
        self.assertRegex(html, r">\s*Jobs\s*</a\s*>")  # navbar link, desktop and mobile panels

    def test_landing_lists_latest_public_postings_only(self) -> None:
        for i in range(4):
            self.make_posting(f"Public role {i}")
        self.make_posting("Secret role", public=False)
        response = self.client.get("/")
        self.assertContains(response, "Public role 3")  # newest first
        self.assertContains(response, "Public role 1")
        self.assertNotContains(response, "Public role 0")  # only 3 shown
        self.assertNotContains(response, "Secret role")

    @override_settings(DEMO_JOBS_ENABLED=True)
    def test_landing_seeds_demo_postings_when_flag_on(self) -> None:
        response = self.client.get("/")
        html = response.content.decode()
        self.assertIn("Demo mode", html)  # demo banner
        # Only the 3 newest postings render, so any seeded title proves seeding.
        self.assertTrue(any(d["title"] in html for d in DEMO_POSTINGS))

    def test_landing_also_renders_for_logged_in_user(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_purple_cta_card_sits_directly_below_the_brand_heading(self) -> None:
        html = self.client.get("/").content.decode()
        cta = html.index("Ready when you are.")
        heading = html.index("text-4xl")  # the hero h1
        tagline = html.index("Paste a job posting.")
        self.assertLess(heading, cta)
        self.assertLess(cta, tagline)  # card is above the tagline, not at the bottom

    def test_dashboard_moved_to_dashboard_path(self) -> None:
        self.assertEqual(reverse("core:dashboard"), "/dashboard/")
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)  # anonymous -> login
        self.assertIn(reverse("login"), response["Location"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your applications")
