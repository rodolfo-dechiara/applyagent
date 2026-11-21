"""The whole LLM provider surface of ApplyAgent.

A single function, chat(), talking to the Mistral chat completions API using
only the standard library (urllib). Swapping providers means swapping only
this file.

Configuration (MISTRAL_API_KEY, MISTRAL_MODEL, MISTRAL_TIMEOUT) is read from
Django settings; explicit keyword arguments override the settings.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

API_URL = "https://api.mistral.ai/v1/chat/completions"

DEFAULT_MODEL = "mistral-small-latest"
DEFAULT_TIMEOUT = 60.0

Message = dict[str, str]


class LLMError(Exception):
    """A clean, user-presentable failure of an LLM call."""


def _setting(name: str, default: str) -> str:
    return getattr(settings, name, default)


def chat(
    messages: list[Message],
    *,
    model: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> str:
    """Send messages to the Mistral chat completions API, return the assistant content.

    Raises LLMError with a user-presentable message on network, HTTP, and
    bad-response-shape failures.
    """
    api_key = api_key if api_key is not None else getattr(settings, "MISTRAL_API_KEY", None)
    model = model or _setting("MISTRAL_MODEL", DEFAULT_MODEL)
    if timeout is None:
        timeout = float(getattr(settings, "MISTRAL_TIMEOUT", DEFAULT_TIMEOUT))
    if not api_key:
        raise LLMError(
            "MISTRAL_API_KEY is not configured. Set it in the environment to use the "
            "Mistral agent, or run in demo mode."
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise LLMError(f"The Mistral API returned HTTP {exc.code}{suffix}.") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Could not reach the Mistral API: {exc.reason}.") from exc
    except TimeoutError as exc:
        raise LLMError("The Mistral API request timed out.") from exc
    except OSError as exc:
        raise LLMError(f"Network error while calling the Mistral API: {exc}.") from exc

    try:
        data: Any = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMError("The Mistral API returned a body that is not valid JSON.") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("The Mistral API returned an unexpected response shape.") from exc
    if not isinstance(content, str):
        raise LLMError("The Mistral API returned an unexpected response shape.")
    return content
