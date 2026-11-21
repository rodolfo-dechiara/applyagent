"""Tests for agent.llm.chat — the whole provider surface, urllib-only.

All network access is mocked: urlopen is patched, no real calls are made.
"""

import io
import json
import unittest
import urllib.error
from typing import Any
from unittest import mock

from django.test import override_settings

from agent.llm import LLMError, chat


def _fake_response(payload: dict[str, Any]) -> mock.MagicMock:
    body = json.dumps(payload).encode("utf-8")
    response = mock.MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


GOOD_PAYLOAD = {"choices": [{"message": {"role": "assistant", "content": '{"ok": true}'}}]}

MESSAGES = [{"role": "user", "content": "hello"}]


class ChatSuccessTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_returns_assistant_content(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response(GOOD_PAYLOAD)
        result = chat(
            MESSAGES,
            model="m",
            api_key="k",
            timeout=30,
            temperature=0.2,
            max_tokens=100,
            json_mode=False,
        )
        self.assertEqual(result, '{"ok": true}')

    @mock.patch("urllib.request.urlopen")
    def test_posts_to_mistral_endpoint_with_auth_header(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response(GOOD_PAYLOAD)
        chat(MESSAGES, model="m", api_key="secret-key", timeout=12, json_mode=False)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.mistral.ai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 12)
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "m")
        self.assertEqual(payload["messages"], MESSAGES)
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 100)
        self.assertNotIn("response_format", payload)

    @mock.patch("urllib.request.urlopen")
    def test_json_mode_adds_response_format(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response(GOOD_PAYLOAD)
        chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=True)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["response_format"], {"type": "json_object"})


class ChatFailureTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_http_error_raises_llmerror_with_status(self, urlopen: mock.MagicMock) -> None:
        error = urllib.error.HTTPError(
            "https://api.mistral.ai/v1/chat/completions",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"message": "bad api key"}'),
        )
        urlopen.side_effect = error
        with self.assertRaises(LLMError) as ctx:
            chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=False)
        self.assertIn("401", str(ctx.exception))

    @mock.patch("urllib.request.urlopen")
    def test_network_error_raises_llmerror(self, urlopen: mock.MagicMock) -> None:
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(LLMError) as ctx:
            chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=False)
        self.assertIn("reach", str(ctx.exception).lower())

    @mock.patch("urllib.request.urlopen")
    def test_timeout_raises_llmerror(self, urlopen: mock.MagicMock) -> None:
        urlopen.side_effect = TimeoutError("timed out")
        with self.assertRaises(LLMError) as ctx:
            chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=False)
        self.assertIn("timed out", str(ctx.exception).lower())

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json_body_raises_llmerror(self, urlopen: mock.MagicMock) -> None:
        response = mock.MagicMock()
        response.read.return_value = b"not json"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        urlopen.return_value = response
        with self.assertRaises(LLMError):
            chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=False)

    @mock.patch("urllib.request.urlopen")
    def test_unexpected_response_shape_raises_llmerror(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response({"unexpected": True})
        with self.assertRaises(LLMError) as ctx:
            chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=False)
        self.assertIn("shape", str(ctx.exception).lower())

    @mock.patch("urllib.request.urlopen")
    def test_non_string_content_raises_llmerror(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response({"choices": [{"message": {"content": None}}]})
        with self.assertRaises(LLMError):
            chat(MESSAGES, model="m", api_key="k", timeout=5, json_mode=False)

    def test_missing_api_key_raises_before_any_network(self) -> None:
        with (
            override_settings(MISTRAL_API_KEY=None),
            mock.patch("urllib.request.urlopen") as urlopen,
            self.assertRaises(LLMError) as ctx,
        ):
            chat(MESSAGES, timeout=5, json_mode=False)
        urlopen.assert_not_called()
        self.assertIn("MISTRAL_API_KEY", str(ctx.exception))


class ChatConfigFromSettingsTests(unittest.TestCase):
    @override_settings(
        MISTRAL_API_KEY="settings-key", MISTRAL_MODEL="settings-model", MISTRAL_TIMEOUT=7
    )
    @mock.patch("urllib.request.urlopen")
    def test_reads_model_key_timeout_from_django_settings(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response(GOOD_PAYLOAD)
        chat(MESSAGES, json_mode=True)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "settings-model")
        self.assertEqual(request.get_header("Authorization"), "Bearer settings-key")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)

    @override_settings(MISTRAL_API_KEY="settings-key")
    @mock.patch("urllib.request.urlopen")
    def test_explicit_kwargs_override_settings(self, urlopen: mock.MagicMock) -> None:
        urlopen.return_value = _fake_response(GOOD_PAYLOAD)
        chat(MESSAGES, model="explicit-model", api_key="explicit-key", timeout=3, json_mode=False)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "explicit-model")
        self.assertEqual(request.get_header("Authorization"), "Bearer explicit-key")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3)
