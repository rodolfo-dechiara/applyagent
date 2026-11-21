"""Application-package generation service.

Two modes:
- "mistral": calls the Mistral chat completions API (see agent.llm) and parses
  the JSON package out of the assistant response.
- "demo": no MISTRAL_API_KEY configured — returns deterministic, clearly-marked
  placeholder output so the full loop works end to end with no network calls.
"""

from __future__ import annotations

import json
import re
from typing import Any


class GenerationError(Exception):
    """A clean, user-presentable failure while generating a package."""


def _json_candidates(text: str) -> list[str]:
    """Yield candidate substrings that might contain the JSON object, best first."""
    stripped = text.strip()
    candidates = [stripped]
    fence = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        candidates.append(stripped[start : end + 1])
    return candidates


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from raw LLM output.

    Recovers from code fences (```json ... ```) and from JSON embedded in
    surrounding prose. Raises GenerationError on anything that is not a JSON
    object.
    """
    for candidate in _json_candidates(text):
        if not candidate:
            continue
        try:
            data: Any = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise GenerationError("The agent returned output that does not contain a valid JSON object.")
