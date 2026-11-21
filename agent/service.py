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
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from agent.llm import DEFAULT_MODEL, DEFAULT_TIMEOUT, LLMError, chat
from agent.prompts import SYSTEM_PROMPT, build_user_prompt
from core.models import JobPosting, Profile


class GenerationError(Exception):
    """A clean, user-presentable failure while generating a package."""


@dataclass(frozen=True)
class ApplicationPackage:
    """The drafted package plus its provenance."""

    tailored_summary: str
    cover_letter: str
    screening_answers: list[dict[str, str]]
    match_score: int | None
    match_reasons: list[str]
    red_flags: list[str]
    mode: str  # "mistral" | "demo"
    model: str


def _json_candidates(text: str) -> list[str]:
    """Return candidate substrings that might contain the JSON object, best first."""
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


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [item for text in value if (item := _as_text(text))]
    text = _as_text(value)
    return [text] if text else []


def _normalize_screening_answers(value: Any) -> list[dict[str, str]]:
    """Coerce the screening_answers field into a list of {"question", "answer"} dicts."""
    if isinstance(value, dict):
        value = [{"question": str(k), "answer": v} for k, v in value.items()]
    answers: list[dict[str, str]] = []
    if not isinstance(value, (list, tuple)):
        value = [value] if value is not None else []
    for item in value:
        if isinstance(item, dict):
            question = _as_text(item.get("question", item.get("q", "")))
            answer = _as_text(item.get("answer", item.get("a", "")))
            if question or answer:
                answers.append({"question": question, "answer": answer})
        else:
            question = _as_text(item)
            if question:
                answers.append({"question": question, "answer": ""})
    return answers


def _clamp_score(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _package_fields_from_json(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the raw JSON object into ApplicationPackage fields."""
    summary = _as_text(data.get("tailored_summary"))
    cover_letter = _as_text(data.get("cover_letter"))
    if not summary:
        raise GenerationError("The agent returned an empty tailored summary.")
    if not cover_letter:
        raise GenerationError("The agent returned an empty cover letter.")
    return {
        "tailored_summary": summary,
        "cover_letter": cover_letter,
        "screening_answers": _normalize_screening_answers(data.get("screening_answers")),
        "match_score": _clamp_score(data.get("match_score")),
        "match_reasons": _as_str_list(data.get("match_reasons")),
        "red_flags": _as_str_list(data.get("red_flags")),
    }


def _demo_score(profile: Profile, job: JobPosting) -> int:
    """Deterministic placeholder score: base 40 plus 10 per distinct skill keyword found."""
    haystack = f"{job.title} {job.description}".lower()
    tokens = re.findall(r"[a-z0-9+#.]+", profile.skills.lower())
    skills = {token for token in tokens if len(token) > 2}
    hits = sum(1 for skill in skills if skill in haystack)
    return max(0, min(100, 40 + 10 * hits))


def _demo_package(profile: Profile, job: JobPosting) -> ApplicationPackage:
    """Deterministic, clearly-marked placeholder package used when no API key is set."""
    score = _demo_score(profile, job)
    headline = profile.headline or "candidate"
    skills = profile.skills or "none listed"
    tailored_summary = (
        f"DEMO OUTPUT: Tailored summary for the {job.title} role at {job.company}. "
        f"{headline} with skills on file: {skills}. "
        "Set MISTRAL_API_KEY to replace this placeholder with a real agent draft."
    )
    cover_letter = (
        f"DEMO OUTPUT: Dear hiring team at {job.company},\n\n"
        f"I am applying for the {job.title} position. This cover letter is a deterministic "
        f"placeholder produced in demo mode (no MISTRAL_API_KEY configured): it is grounded "
        f"only in the profile on file ({headline}; skills: {skills}) and invents nothing. "
        "Set MISTRAL_API_KEY to get a real agent-drafted letter.\n\n"
        "Sincerely,\nThe candidate"
    )
    screening_answers = [
        {
            "question": f"DEMO OUTPUT: Why do you want to work at {job.company}?",
            "answer": "DEMO OUTPUT: placeholder answer — demo mode, no API key configured.",
        },
        {
            "question": "DEMO OUTPUT: What is your availability?",
            "answer": "DEMO OUTPUT: placeholder answer — demo mode, no API key configured.",
        },
    ]
    match_reasons = [
        "DEMO OUTPUT: placeholder reason — deterministic demo scoring based on skill "
        f"keywords from the profile found in the posting (score {score}/100)."
    ]
    red_flags = [
        "DEMO OUTPUT: this package was generated in demo mode; review it carefully.",
    ]
    if not profile.cv_text.strip():
        red_flags.append("DEMO OUTPUT: your profile has no CV text on file.")
    if not profile.links.strip():
        red_flags.append("DEMO OUTPUT: your profile has no links (portfolio, LinkedIn, ...).")
    return ApplicationPackage(
        tailored_summary=tailored_summary,
        cover_letter=cover_letter,
        screening_answers=screening_answers,
        match_score=score,
        match_reasons=match_reasons,
        red_flags=red_flags,
        mode="demo",
        model="demo",
    )


def generate_application_package(profile: Profile, job: JobPosting) -> ApplicationPackage:
    """Generate the full application package for a job posting, in mistral or demo mode.

    Raises GenerationError with a user-presentable message on any failure.
    """
    api_key = getattr(settings, "MISTRAL_API_KEY", None)
    if not api_key:
        return _demo_package(profile, job)
    model = str(getattr(settings, "MISTRAL_MODEL", DEFAULT_MODEL))
    timeout = float(getattr(settings, "MISTRAL_TIMEOUT", DEFAULT_TIMEOUT))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(profile, job)},
    ]
    try:
        raw = chat(
            messages,
            model=model,
            api_key=api_key,
            timeout=timeout,
            temperature=0.2,
            max_tokens=4096,
            json_mode=True,
        )
    except LLMError as exc:
        raise GenerationError(str(exc)) from exc
    data = extract_json(raw)
    fields = _package_fields_from_json(data)
    return ApplicationPackage(**fields, mode="mistral", model=model)
