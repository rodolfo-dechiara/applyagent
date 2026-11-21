"""Tests for agent.service — starting with the extract_json recovery cases."""

import unittest

from agent.service import GenerationError, extract_json


class ExtractJsonTests(unittest.TestCase):
    def test_plain_json_object(self) -> None:
        result = extract_json('{"a": 1, "b": "x"}')
        self.assertEqual(result, {"a": 1, "b": "x"})

    def test_fenced_json_with_language_tag(self) -> None:
        result = extract_json('```json\n{"a": 1}\n```')
        self.assertEqual(result, {"a": 1})

    def test_fenced_json_without_language_tag(self) -> None:
        result = extract_json('```\n{"a": 2}\n```')
        self.assertEqual(result, {"a": 2})

    def test_json_inside_surrounding_prose(self) -> None:
        text = (
            "Here is the package you asked for:\n"
            '{"a": 3, "nested": {"k": [1, 2]}}\n'
            "Hope this helps!"
        )
        result = extract_json(text)
        self.assertEqual(result, {"a": 3, "nested": {"k": [1, 2]}})

    def test_fenced_json_inside_surrounding_prose(self) -> None:
        text = 'Sure! ```json\n{"a": 4}\n``` Let me know if you need changes.'
        result = extract_json(text)
        self.assertEqual(result, {"a": 4})

    def test_garbage_raises(self) -> None:
        with self.assertRaises(GenerationError):
            extract_json("this is not json at all")

    def test_empty_string_raises(self) -> None:
        with self.assertRaises(GenerationError):
            extract_json("   ")

    def test_valid_json_non_object_raises(self) -> None:
        with self.assertRaises(GenerationError):
            extract_json("[1, 2, 3]")

    def test_truncated_json_raises(self) -> None:
        with self.assertRaises(GenerationError):
            extract_json('{"a": 1, "b": ')
