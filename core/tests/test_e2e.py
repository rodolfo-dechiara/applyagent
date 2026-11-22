"""End-to-end tests: real Chromium (Playwright, pip-installed — no node/npm)
driving the full user loop against a live Django server, in demo mode.

Run with: uv run python manage.py test core.tests.test_e2e
Requires the browser once per environment: uv run playwright install --with-deps chromium
"""

import re

from django.core import mail
from django.core.cache import cache
from django.test import LiveServerTestCase, override_settings, tag
from playwright.sync_api import Page, sync_playwright

from core.tests.utils import PASSWORD, VERIFY_LINK_RE

MOBILE = {"width": 390, "height": 844}  # iPhone-ish
DESKTOP = {"width": 1280, "height": 800}


def assert_no_horizontal_overflow(page: Page) -> None:
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1, f"horizontal overflow of {overflow}px at {page.viewport_size}"


def submit_and_wait(page: Page, url_pattern: str) -> None:
    """Click the main form's submit button, wait for the redirect, assert the URL."""
    with page.expect_navigation(wait_until="domcontentloaded"):
        page.click("main button[type='submit']")
    assert re.search(url_pattern, page.url), f"expected {url_pattern!r}, got {page.url}"


def register_verify_login(page: Page, base_url: str, username: str) -> None:
    """Register, click the emailed verification link, land on the dashboard."""
    page.goto(f"{base_url}/accounts/register/", wait_until="domcontentloaded")
    page.fill("input[name='username']", username)
    page.fill("input[name='email']", f"{username}@example.com")
    page.fill("input[name='password1']", PASSWORD)
    page.fill("input[name='password2']", PASSWORD)
    submit_and_wait(page, r"/accounts/register/done/$")
    assert mail.outbox, "verification email not sent"
    match = VERIFY_LINK_RE.search(str(mail.outbox[-1].body))
    assert match, "no verification link in the email"
    page.goto(f"{base_url}{match.group(0)}", wait_until="domcontentloaded")
    page.wait_for_selector("text=Your applications")


def fill_profile_and_paste_job(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/profile/", wait_until="domcontentloaded")
    page.fill("input[name='headline']", "Backend engineer")
    page.fill("textarea[name='skills']", "Python, Django, SQL")
    page.fill("textarea[name='experience']", "5 years at Acme")
    page.fill("textarea[name='education']", "MSc CS")
    page.fill("textarea[name='links']", "https://example.com/alice")
    page.fill("textarea[name='cv_text']", "Alice CV body")
    submit_and_wait(page, rf"^{re.escape(base_url)}/dashboard/$")

    page.goto(f"{base_url}/jobs/new/", wait_until="domcontentloaded")
    page.fill("input[name='title']", "Django developer")
    page.fill("input[name='company']", "Acme Corp")
    page.fill("textarea[name='description']", "Build APIs with Django, Python and SQL.")
    page.fill("input[name='source_url']", "https://jobs.example.com/1")
    submit_and_wait(page, r"/applications/[0-9A-HJKMNP-TV-Z*~$@+]{25}/$")
    page.wait_for_selector("section#package")


@tag("e2e")
@override_settings(MISTRAL_API_KEY=None)
class EndToEndTests(LiveServerTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_mobile_full_loop(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport=MOBILE)
            base = self.live_server_url

            # Landing page is public: brand + jobs CTA, no overflow on mobile;
            # the Jobs link is visible in the hamburger panel.
            page.goto(f"{base}/", wait_until="domcontentloaded")
            page.wait_for_selector("text=You're Hired")
            page.locator("main >> text=Browse jobs").first.wait_for(state="visible")
            assert_no_horizontal_overflow(page)
            page.click("button[aria-label='Toggle navigation menu']")
            page.locator("nav >> text=Jobs").last.wait_for(state="visible")
            assert_no_horizontal_overflow(page)

            # Login page: no overflow, hamburger visible, desktop links hidden.
            page.goto(f"{base}/accounts/login/", wait_until="domcontentloaded")
            assert_no_horizontal_overflow(page)
            assert page.is_visible("button[aria-label='Toggle navigation menu']")
            assert not page.is_visible("nav .md\\:flex a")  # desktop-only links
            page.click("button[aria-label='Toggle navigation menu']")
            # The mobile menu panel is the last Register link in the nav DOM.
            page.locator("nav >> text=Register").last.wait_for(state="visible")
            assert_no_horizontal_overflow(page)

            # Public job board is reachable anonymously, with empty state (flag off).
            page.goto(f"{base}/jobs/", wait_until="domcontentloaded")
            page.wait_for_selector("text=No public job postings yet")
            assert_no_horizontal_overflow(page)

            register_verify_login(page, base, "mobileuser")
            assert_no_horizontal_overflow(page)

            fill_profile_and_paste_job(page, base)
            assert_no_horizontal_overflow(page)
            page.wait_for_selector("text=DEMO OUTPUT")
            page.wait_for_selector("text=Tailored summary")
            page.wait_for_selector("text=Red flags")

            # HTMX regenerate swaps the partial without a reload.
            with page.expect_response(lambda r: "/regenerate/" in r.url) as response_info:
                page.click("text=Regenerate with the agent")
            response = response_info.value
            assert response.status == 200
            page.wait_for_selector("section#package >> text=DEMO OUTPUT")

            # Human review pass.
            page.click("text=Edit (review pass)")
            page.wait_for_url("**/edit/")
            page.fill("textarea[name='tailored_summary']", "My edited summary.")
            page.fill("textarea[name='cover_letter']", "My edited letter.")
            submit_and_wait(page, r"/applications/[0-9A-HJKMNP-TV-Z*~$@+]{25}/$")
            page.wait_for_selector("text=My edited summary.")

            # Status transition button.
            page.click("button[title='Mark as Ready']")
            page.wait_for_selector("text=Ready")

            # Delete removes application and posting.
            with page.expect_navigation(wait_until="domcontentloaded"):
                page.click("text=Delete")
            assert re.search(r"/delete/$", page.url), page.url
            submit_and_wait(page, f"{base}/dashboard/")
            page.wait_for_selector("text=No applications yet")
            assert_no_horizontal_overflow(page)

            browser.close()

    def test_desktop_full_loop(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport=DESKTOP)
            base = self.live_server_url

            page.goto(f"{base}/accounts/login/", wait_until="domcontentloaded")
            assert_no_horizontal_overflow(page)
            # Desktop: inline nav links, no hamburger.
            page.locator("nav >> text=Log in").first.wait_for(state="visible")
            assert not page.is_visible("button[aria-label='Toggle navigation menu']")

            register_verify_login(page, base, "desktopuser")
            page.locator("nav >> text=Paste a job").first.wait_for(state="visible")
            assert_no_horizontal_overflow(page)

            fill_profile_and_paste_job(page, base)
            page.wait_for_selector("text=Match score")
            page.wait_for_selector("text=/100")
            assert_no_horizontal_overflow(page)

            browser.close()

    def test_all_auth_pages_have_no_overflow_on_mobile(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 360, "height": 740})
            base = self.live_server_url
            for path in [
                "/",
                "/accounts/login/",
                "/accounts/register/",
                "/accounts/verify/resend/",
                "/accounts/password-reset/",
                "/jobs/",
            ]:
                with self.subTest(path=path):
                    page.goto(f"{base}{path}", wait_until="domcontentloaded")
                    assert_no_horizontal_overflow(page)
            browser.close()

    def test_landing_scroll_reveal_animation(self) -> None:
        """Below-fold cards start hidden and reveal (opacity -> 1) on scroll."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport=DESKTOP)
            base = self.live_server_url
            page.goto(f"{base}/", wait_until="domcontentloaded")
            card = page.locator("#features .reveal").first
            card.wait_for(state="attached")
            before = float(card.evaluate("el => getComputedStyle(el).opacity"))
            assert before < 0.5, f"card should start hidden, got opacity {before}"
            card.scroll_into_view_if_needed()
            page.wait_for_selector("#features .reveal.revealed", timeout=5000)
            after = float(card.evaluate("el => getComputedStyle(el).opacity"))
            assert after > 0.9, f"card should be revealed after scroll, got opacity {after}"
            assert_no_horizontal_overflow(page)
            browser.close()

    @override_settings(MISTRAL_API_KEY=None, DEMO_JOBS_ENABLED=True)
    def test_mobile_board_demo_flag_apply_flow(self) -> None:
        """With the demo flag on, the board shows marked fake postings and a
        logged-in candidate can apply to one straight from the board."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport=MOBILE)
            base = self.live_server_url

            register_verify_login(page, base, "boarduser")
            page.goto(f"{base}/jobs/", wait_until="domcontentloaded")
            page.wait_for_selector("text=Demo mode is on")
            page.wait_for_selector("text=Senior Backend Engineer")
            assert_no_horizontal_overflow(page)

            with page.expect_navigation(wait_until="domcontentloaded"):
                page.locator("main a", has_text="Senior Backend Engineer").first.click()
            assert re.search(r"/jobs/[0-9A-HJKMNP-TV-Z*~$@+]{25}/$", page.url), page.url
            assert_no_horizontal_overflow(page)

            # POST the apply form -> own application page with a demo package.
            submit_and_wait(page, r"/applications/[0-9A-HJKMNP-TV-Z*~$@+]{25}/$")
            page.wait_for_selector("section#package >> text=DEMO OUTPUT")
            assert_no_horizontal_overflow(page)

            browser.close()
