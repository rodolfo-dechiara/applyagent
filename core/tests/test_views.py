"""View tests for the core app — written before the views exist (TDD red)."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Application, JobPosting, Profile

PASSWORD = "Str0ng!Pass99"


class ViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.client.force_login(self.user)

    def make_profile(self, user: User | None = None) -> Profile:
        return Profile.objects.create(
            user=user or self.user,
            headline="Backend engineer",
            skills="Python, Django, SQL",
            experience="5 years at Acme",
            education="MSc CS",
            links="https://example.com/alice",
            cv_text="Alice CV body",
        )

    def make_job(self, owner: User | None = None) -> JobPosting:
        return JobPosting.objects.create(
            owner=owner or self.user,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs with Django, Python and SQL.",
            source_url="https://jobs.example.com/1",
        )

    def make_application(
        self, user: User | None = None, job: JobPosting | None = None
    ) -> Application:
        user = user or self.user
        job = job or self.make_job(owner=user)
        return Application.objects.create(
            job=job,
            user=user,
            tailored_summary="DEMO OUTPUT: summary",
            cover_letter="DEMO OUTPUT: letter",
            screening_answers=[{"question": "DEMO OUTPUT: Q?", "answer": "DEMO OUTPUT: A"}],
            match_score=70,
            match_reasons=["DEMO OUTPUT: reason"],
            red_flags=["DEMO OUTPUT: flag"],
            agent_mode="demo",
            agent_model="demo",
        )


class DashboardTests(ViewTestCase):
    def test_anonymous_is_redirected_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_empty_state_when_no_applications(self) -> None:
        self.make_profile()
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No applications yet")

    def test_nudge_when_no_profile_exists(self) -> None:
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profile")
        self.assertContains(response, reverse("core:profile"))

    def test_no_nudge_once_profile_exists(self) -> None:
        self.make_profile()
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "haven't created your profile")

    def test_lists_applications_with_status(self) -> None:
        app = self.make_application()
        self.make_profile()
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Django developer")
        self.assertContains(response, "Acme Corp")
        self.assertContains(response, "Draft")
        self.assertContains(response, reverse("core:application_detail", args=[app.pk]))


class RegisterAndLoginTests(TestCase):
    def test_register_page_renders(self) -> None:
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)

    def test_register_creates_user_logs_in_and_redirects_to_dashboard(self) -> None:
        response = self.client.post(
            reverse("register"),
            {
                "username": "newbie",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:dashboard"))
        user = User.objects.get(username="newbie")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_register_rejects_mismatched_passwords(self) -> None:
        response = self.client.post(
            reverse("register"),
            {"username": "newbie", "password1": PASSWORD, "password2": "Different!Pass1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_login_page_renders(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_login_with_django_auth_view(self) -> None:
        User.objects.create_user(username="bob", password=PASSWORD)
        response = self.client.post(reverse("login"), {"username": "bob", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:dashboard"))


class ProfileTests(ViewTestCase):
    def test_get_renders_form(self) -> None:
        response = self.client.get(reverse("core:profile"))
        self.assertEqual(response.status_code, 200)

    def test_first_save_creates_profile(self) -> None:
        response = self.client.post(
            reverse("core:profile"),
            {
                "headline": "Backend engineer",
                "skills": "Python, Django",
                "experience": "5 years",
                "education": "MSc",
                "links": "https://example.com",
                "cv_text": "CV body",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.headline, "Backend engineer")
        self.assertEqual(profile.skills, "Python, Django")

    def test_second_save_updates_same_profile(self) -> None:
        self.make_profile()
        response = self.client.post(
            reverse("core:profile"),
            {
                "headline": "Staff engineer",
                "skills": "Python",
                "experience": "8 years",
                "education": "MSc",
                "links": "",
                "cv_text": "CV body 2",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Profile.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Profile.objects.get(user=self.user).headline, "Staff engineer")

    def test_anonymous_is_redirected(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("core:profile"))
        self.assertEqual(response.status_code, 302)


@override_settings(MISTRAL_API_KEY=None)
class JobPasteTests(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_profile()

    def test_get_renders_form(self) -> None:
        response = self.client.get(reverse("core:job_new"))
        self.assertEqual(response.status_code, 200)

    def test_paste_generates_demo_package_and_redirects_to_application(self) -> None:
        response = self.client.post(
            reverse("core:job_new"),
            {
                "title": "Django developer",
                "company": "Acme Corp",
                "description": "Build APIs with Django, Python and SQL.",
                "source_url": "https://jobs.example.com/1",
            },
        )
        job = JobPosting.objects.get(title="Django developer")
        app = Application.objects.get(job=job)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:application_detail", args=[app.pk]))
        self.assertEqual(job.owner, self.user)
        self.assertEqual(app.user, self.user)
        self.assertEqual(app.status, Application.Status.DRAFT)
        self.assertEqual(app.agent_mode, "demo")
        self.assertTrue(app.tailored_summary.startswith("DEMO OUTPUT:"))
        self.assertTrue(app.cover_letter.startswith("DEMO OUTPUT:"))
        self.assertTrue(app.screening_answers)
        self.assertIsNotNone(app.match_score)
        self.assertIsNotNone(app.generated_at)
        follow = self.client.get(response["Location"])
        self.assertEqual(follow.status_code, 200)

    def test_paste_sends_review_message(self) -> None:
        response = self.client.post(
            reverse("core:job_new"),
            {
                "title": "Django developer",
                "company": "Acme Corp",
                "description": "Build APIs with Django.",
                "source_url": "",
            },
            follow=True,
        )
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("review" in m.lower() for m in messages))

    def test_invalid_post_creates_nothing(self) -> None:
        response = self.client.post(
            reverse("core:job_new"), {"title": "", "company": "", "description": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JobPosting.objects.count(), 0)
        self.assertEqual(Application.objects.count(), 0)


class ApplicationDetailTests(ViewTestCase):
    def test_detail_renders_all_package_sections(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_detail", args=[app.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django developer")
        self.assertContains(response, "Acme Corp")
        self.assertContains(response, "DEMO OUTPUT: summary")
        self.assertContains(response, "DEMO OUTPUT: letter")
        self.assertContains(response, "DEMO OUTPUT: Q?")
        self.assertContains(response, "DEMO OUTPUT: A")
        self.assertContains(response, "70/100")
        self.assertContains(response, "DEMO OUTPUT: reason")
        self.assertContains(response, "DEMO OUTPUT: flag")
        self.assertContains(response, "demo")

    def test_detail_shows_status_buttons_for_every_status_except_current(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_detail", args=[app.pk]))
        for value, _label in Application.Status.choices:
            if value == app.status:
                self.assertNotContains(response, f'value="{value}"')
            else:
                self.assertContains(response, f'value="{value}"')

    def test_detail_has_edit_delete_regenerate_links(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_detail", args=[app.pk]))
        self.assertContains(response, reverse("core:application_edit", args=[app.pk]))
        self.assertContains(response, reverse("core:application_delete", args=[app.pk]))
        self.assertContains(response, reverse("core:application_regenerate", args=[app.pk]))


@override_settings(MISTRAL_API_KEY=None)
class RegenerateTests(ViewTestCase):
    def test_htmx_post_returns_package_partial_with_200(self) -> None:
        app = self.make_application()
        old_generated_at = app.generated_at
        response = self.client.post(
            reverse("core:application_regenerate", args=[app.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="package"')
        self.assertContains(response, "DEMO OUTPUT")
        app.refresh_from_db()
        self.assertEqual(Application.objects.count(), 1)
        self.assertNotEqual(app.generated_at, old_generated_at)

    def test_plain_post_redirects_to_detail(self) -> None:
        app = self.make_application()
        response = self.client.post(reverse("core:application_regenerate", args=[app.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:application_detail", args=[app.pk]))

    def test_get_is_not_allowed(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_regenerate", args=[app.pk]))
        self.assertEqual(response.status_code, 405)


class EditTests(ViewTestCase):
    def test_get_shows_current_values(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_edit", args=[app.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DEMO OUTPUT: summary")
        self.assertContains(response, "DEMO OUTPUT: letter")

    def test_post_saves_edited_summary_and_letter(self) -> None:
        app = self.make_application()
        response = self.client.post(
            reverse("core:application_edit", args=[app.pk]),
            {
                "tailored_summary": "Human-edited summary.",
                "cover_letter": "Human-edited letter.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:application_detail", args=[app.pk]))
        app.refresh_from_db()
        self.assertEqual(app.tailored_summary, "Human-edited summary.")
        self.assertEqual(app.cover_letter, "Human-edited letter.")
        # Other package fields are untouched by the edit.
        self.assertEqual(app.match_score, 70)
        self.assertEqual(app.red_flags, ["DEMO OUTPUT: flag"])


class StatusTests(ViewTestCase):
    def test_every_valid_status_transition_works(self) -> None:
        app = self.make_application()
        for value, _label in Application.Status.choices:
            if value == app.status:
                continue
            response = self.client.post(
                reverse("core:application_status", args=[app.pk]), {"status": value}
            )
            self.assertEqual(response.status_code, 302)
            app.refresh_from_db()
            self.assertEqual(app.status, value)

    def test_unknown_status_is_refused_with_message(self) -> None:
        app = self.make_application()
        response = self.client.post(
            reverse("core:application_status", args=[app.pk]),
            {"status": "bogus"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("bogus" in m for m in messages))
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.DRAFT)

    def test_get_is_not_allowed(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_status", args=[app.pk]))
        self.assertEqual(response.status_code, 405)


class DeleteTests(ViewTestCase):
    def test_get_shows_confirmation(self) -> None:
        app = self.make_application()
        response = self.client.get(reverse("core:application_delete", args=[app.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django developer")

    def test_post_deletes_application_and_posting(self) -> None:
        app = self.make_application()
        job_pk = app.job.pk
        response = self.client.post(reverse("core:application_delete", args=[app.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:dashboard"))
        self.assertFalse(Application.objects.filter(pk=app.pk).exists())
        self.assertFalse(JobPosting.objects.filter(pk=job_pk).exists())
