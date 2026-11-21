"""Tests for generate_application_package: demo mode shape, validation, mistral path."""

import unittest
from typing import Any
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from agent.llm import LLMError
from agent.service import GenerationError, generate_application_package
from core.models import JobPosting, Profile


class ServiceTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password="pw12345!")
        self.profile = Profile.objects.create(
            user=self.user,
            headline="Backend engineer",
            skills="Python, Django, SQL",
            experience="5 years at Acme",
            education="MSc CS",
            links="https://example.com/alice",
            cv_text="Alice CV body",
        )
        self.job = JobPosting.objects.create(
            owner=self.user,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs with Django, Python and SQL.",
            source_url="https://jobs.example.com/1",
        )


@override_settings(MISTRAL_API_KEY=None)
class DemoPackageTests(ServiceTestCase):
    def test_demo_package_has_the_right_shape(self) -> None:
        package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.mode, "demo")
        self.assertEqual(package.model, "demo")
        self.assertTrue(package.tailored_summary.startswith("DEMO OUTPUT:"))
        self.assertTrue(package.cover_letter.startswith("DEMO OUTPUT:"))
        self.assertTrue(package.tailored_summary.strip())
        self.assertTrue(package.cover_letter.strip())
        self.assertIsNotNone(package.match_score)
        assert package.match_score is not None
        self.assertGreaterEqual(package.match_score, 0)
        self.assertLessEqual(package.match_score, 100)
        self.assertIsInstance(package.screening_answers, list)
        self.assertTrue(package.screening_answers)
        for qa in package.screening_answers:
            self.assertIsInstance(qa, dict)
            self.assertIn("question", qa)
            self.assertIn("answer", qa)
            self.assertTrue(qa["question"].startswith("DEMO OUTPUT:"))
            self.assertTrue(qa["answer"].startswith("DEMO OUTPUT:"))
        for reason in package.match_reasons:
            self.assertIsInstance(reason, str)
            self.assertTrue(reason)
        for flag in package.red_flags:
            self.assertIsInstance(flag, str)
            self.assertTrue(flag)

    def test_demo_package_mentions_job_and_is_deterministic(self) -> None:
        first = generate_application_package(self.profile, self.job)
        second = generate_application_package(self.profile, self.job)
        self.assertEqual(first, second)
        self.assertIn("Acme Corp", first.cover_letter)
        self.assertIn("Django developer", first.tailored_summary)

    def test_demo_mode_makes_no_network_calls(self) -> None:
        with mock.patch("agent.service.chat") as chat_mock:
            generate_application_package(self.profile, self.job)
        chat_mock.assert_not_called()


def _valid_payload(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "tailored_summary": "A tailored summary.",
        "cover_letter": "Dear Acme Corp, ...",
        "screening_answers": [{"question": "Why us?", "answer": "Because of Django."}],
        "match_score": 82,
        "match_reasons": ["Strong Django experience"],
        "red_flags": ["No portfolio link"],
    }
    payload.update(overrides)
    import json

    return json.dumps(payload)


@override_settings(MISTRAL_API_KEY="test-key", MISTRAL_MODEL="test-model", MISTRAL_TIMEOUT=30)
class MistralPackageTests(ServiceTestCase):
    def test_valid_response_is_parsed_into_fields(self) -> None:
        with mock.patch("agent.service.chat", return_value=_valid_payload()) as chat_mock:
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.mode, "mistral")
        self.assertEqual(package.model, "test-model")
        self.assertEqual(package.tailored_summary, "A tailored summary.")
        self.assertEqual(package.cover_letter, "Dear Acme Corp, ...")
        self.assertEqual(
            package.screening_answers, [{"question": "Why us?", "answer": "Because of Django."}]
        )
        self.assertEqual(package.match_score, 82)
        self.assertEqual(package.match_reasons, ["Strong Django experience"])
        self.assertEqual(package.red_flags, ["No portfolio link"])
        messages = chat_mock.call_args.args[0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("CANDIDATE PROFILE", messages[1]["content"])
        self.assertIn("JOB POSTING", messages[1]["content"])
        self.assertTrue(chat_mock.call_args.kwargs["json_mode"])

    def test_recovers_fenced_json_with_prose(self) -> None:
        raw = f"Here you go!\n```json\n{_valid_payload()}\n```\nDone."
        with mock.patch("agent.service.chat", return_value=raw):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.match_score, 82)

    def test_score_is_clamped_to_0_100(self) -> None:
        with mock.patch("agent.service.chat", return_value=_valid_payload(match_score=250)):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.match_score, 100)
        with mock.patch("agent.service.chat", return_value=_valid_payload(match_score=-3)):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.match_score, 0)

    def test_non_numeric_score_becomes_none(self) -> None:
        with mock.patch("agent.service.chat", return_value=_valid_payload(match_score="abc")):
            package = generate_application_package(self.profile, self.job)
        self.assertIsNone(package.match_score)

    def test_string_score_is_coerced(self) -> None:
        with mock.patch("agent.service.chat", return_value=_valid_payload(match_score="77")):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.match_score, 77)

    def test_screening_answers_dict_is_coerced(self) -> None:
        payload = _valid_payload(screening_answers={"Why us?": "Django"})
        with mock.patch("agent.service.chat", return_value=payload):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.screening_answers, [{"question": "Why us?", "answer": "Django"}])

    def test_screening_answers_strings_are_coerced(self) -> None:
        payload = _valid_payload(screening_answers=["Why us?"])
        with mock.patch("agent.service.chat", return_value=payload):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.screening_answers, [{"question": "Why us?", "answer": ""}])

    def test_list_fields_given_as_string_are_coerced(self) -> None:
        payload = _valid_payload(match_reasons="one reason", red_flags=None)
        with mock.patch("agent.service.chat", return_value=payload):
            package = generate_application_package(self.profile, self.job)
        self.assertEqual(package.match_reasons, ["one reason"])
        self.assertEqual(package.red_flags, [])

    def test_empty_tailored_summary_fails(self) -> None:
        with (
            mock.patch("agent.service.chat", return_value=_valid_payload(tailored_summary="  ")),
            self.assertRaises(GenerationError),
        ):
            generate_application_package(self.profile, self.job)

    def test_empty_cover_letter_fails(self) -> None:
        with (
            mock.patch("agent.service.chat", return_value=_valid_payload(cover_letter="")),
            self.assertRaises(GenerationError),
        ):
            generate_application_package(self.profile, self.job)

    def test_garbage_response_raises_generation_error(self) -> None:
        with (
            mock.patch("agent.service.chat", return_value="not json at all"),
            self.assertRaises(GenerationError),
        ):
            generate_application_package(self.profile, self.job)

    def test_llm_error_is_wrapped_in_generation_error(self) -> None:
        with (
            mock.patch("agent.service.chat", side_effect=LLMError("boom: HTTP 500")),
            self.assertRaises(GenerationError) as ctx,
        ):
            generate_application_package(self.profile, self.job)
        self.assertIn("boom: HTTP 500", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
