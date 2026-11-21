"""Tests for agent.prompts: the system prompt contract and the user-prompt builder."""

import unittest

from django.contrib.auth.models import User
from django.test import TestCase

from agent.prompts import SYSTEM_PROMPT, build_user_prompt
from core.models import JobPosting, Profile

PACKAGE_KEYS = [
    "tailored_summary",
    "cover_letter",
    "screening_answers",
    "match_score",
    "match_reasons",
    "red_flags",
]


class SystemPromptTests(unittest.TestCase):
    def test_demands_exactly_the_six_package_keys(self) -> None:
        for key in PACKAGE_KEYS:
            self.assertIn(key, SYSTEM_PROMPT)
        self.assertIn("exactly", SYSTEM_PROMPT.lower())
        self.assertIn("one json object", SYSTEM_PROMPT.lower())

    def test_forbids_inventing_facts_about_the_candidate(self) -> None:
        lowered = SYSTEM_PROMPT.lower()
        self.assertIn("never invent", lowered)
        self.assertIn("fabricat", lowered)

    def test_missing_information_goes_to_red_flags_not_the_letter(self) -> None:
        lowered = SYSTEM_PROMPT.lower()
        self.assertIn("red_flags", lowered)
        self.assertIn("cover letter", lowered)

    def test_grounded_in_the_candidate_profile(self) -> None:
        self.assertIn("CANDIDATE PROFILE", SYSTEM_PROMPT)


class BuildUserPromptTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password="pw12345!")
        self.profile = Profile.objects.create(
            user=self.user,
            headline="Backend engineer",
            skills="Python, Django",
            experience="5 years at Acme",
            education="MSc CS",
            links="https://example.com/alice",
            cv_text="Alice CV body",
        )
        self.job = JobPosting.objects.create(
            owner=self.user,
            title="Django developer",
            company="Acme Corp",
            description="Build APIs with Django and SQL.",
            source_url="https://jobs.example.com/1",
        )

    def test_has_explicit_profile_and_job_sections(self) -> None:
        prompt = build_user_prompt(self.profile, self.job)
        self.assertIn("CANDIDATE PROFILE", prompt)
        self.assertIn("JOB POSTING", prompt)
        self.assertLess(prompt.index("CANDIDATE PROFILE"), prompt.index("JOB POSTING"))

    def test_includes_profile_values(self) -> None:
        prompt = build_user_prompt(self.profile, self.job)
        values = [
            "Backend engineer",
            "Python, Django",
            "5 years at Acme",
            "MSc CS",
            "Alice CV body",
        ]
        for value in values:
            self.assertIn(value, prompt)

    def test_includes_job_values(self) -> None:
        prompt = build_user_prompt(self.profile, self.job)
        for value in ["Django developer", "Acme Corp", "Build APIs with Django and SQL."]:
            self.assertIn(value, prompt)


if __name__ == "__main__":
    unittest.main()
