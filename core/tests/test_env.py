"""Tests for the stdlib .env parser used by config.settings."""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from config.settings import parse_env_file


class ParseEnvFileTests(SimpleTestCase):
    def write_env(self, text: str) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write(text)
        return Path(handle.name)

    def test_parses_key_value_pairs(self) -> None:
        path = self.write_env("MISTRAL_API_KEY=abc123\nDEBUG=True\n")
        self.assertEqual(parse_env_file(path), {"MISTRAL_API_KEY": "abc123", "DEBUG": "True"})

    def test_skips_comments_and_blank_lines(self) -> None:
        path = self.write_env("# comment\n\n  \nKEY=value\n# another\n")
        self.assertEqual(parse_env_file(path), {"KEY": "value"})

    def test_strips_surrounding_quotes(self) -> None:
        path = self.write_env("A=\"quoted value\"\nB='single'\n")
        self.assertEqual(parse_env_file(path), {"A": "quoted value", "B": "single"})

    def test_value_may_contain_equals(self) -> None:
        path = self.write_env("KEY=abc=def==\n")
        self.assertEqual(parse_env_file(path), {"KEY": "abc=def=="})

    def test_lines_without_equals_are_ignored(self) -> None:
        path = self.write_env("not a pair\nKEY=value\n")
        self.assertEqual(parse_env_file(path), {"KEY": "value"})

    def test_missing_file_returns_empty_dict(self) -> None:
        self.assertEqual(parse_env_file(Path("/nonexistent/.env")), {})
