"""Detection signal implementations for Provenance Guard Milestone 3.

Milestone 3 only wires the first signal into /submit. Signal 2 and final
confidence calibration are intentionally left for Milestone 4.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

Verdict = Literal["human", "ai", "uncertain"]


@dataclass(frozen=True)
class LlmSignalResult:
    signal: str
    ai_score: float
    verdict: Verdict
    rationale: str
    limitations: list[str]
    mocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SignalError(RuntimeError):
    """Raised when a detection signal cannot produce a valid result."""


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise SignalError("LLM response did not include a numeric ai_score.") from exc
    return max(0.0, min(1.0, score))


def _normalize_verdict(value: Any, ai_score: float) -> Verdict:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"human", "ai", "uncertain"}:
            return normalized  # type: ignore[return-value]

    if ai_score >= 0.85:
        return "ai"
    if ai_score <= 0.15:
        return "human"
    return "uncertain"


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from the model response.

    Groq usually returns clean JSON when response_format is requested, but this
    defensive parser also accepts a response that includes surrounding text.
    """
    raw_text = raw_text.strip()
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if not match:
        raise SignalError("LLM response did not contain a JSON object.")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise SignalError("LLM response JSON was malformed.") from exc

    if not isinstance(parsed, dict):
        raise SignalError("LLM response JSON was not an object.")
    return parsed


def _mock_llm_signal(text: str) -> LlmSignalResult:
    """Explicit local fallback for route/audit-log testing without a Groq key.

    This is not the final detection logic. It exists so Milestone 3 can be run
    locally before secrets are configured. The response marks mocked=True.
    """
    lowered = text.lower()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ai_markers = (
        "as an ai",
        "in conclusion",
        "it is important to note",
        "moreover",
        "furthermore",
        "delve",
        "tapestry",
    )
    human_markers = ("i ", "my ", "me ", "coffee", "porch", "yesterday", "mom", "dad")

    marker_score = sum(1 for marker in ai_markers if marker in lowered) * 0.12
    personal_score = sum(1 for marker in human_markers if marker in lowered) * -0.06
    length_adjustment = 0.08 if len(text.split()) < 40 else 0.0
    hash_noise = (int(text_hash[:2], 16) / 255.0 - 0.5) * 0.04
    score = max(0.05, min(0.95, 0.5 + marker_score + personal_score + length_adjustment + hash_noise))

    return LlmSignalResult(
        signal="groq_llm",
        ai_score=round(score, 3),
        verdict=_normalize_verdict(None, score),
        rationale="Local mock result used because Groq is not configured or fallback is enabled.",
        limitations=[
            "This is not a real Groq classification.",
            "Use GROQ_API_KEY for the required LLM-backed signal.",
        ],
        mocked=True,
    )


def _build_prompt(cleaned_text: str) -> str:
    clipped_text = cleaned_text[:8000]
    return f'''You are Signal 1 for a student project called Provenance Guard.
Classify whether the submitted text appears more likely human-written,
AI-generated, or uncertain.

Return ONLY a JSON object with this exact schema:
{{
  "ai_score": 0.0,
  "verdict": "human | ai | uncertain",
  "rationale": "one short sentence",
  "limitations": ["one or two concrete blind spots"]
}}

Score semantics:
- 0.00 means strongly human-like.
- 0.50 means uncertain or mixed evidence.
- 1.00 means strongly AI-like.

Do not claim proof of authorship. Penalize overconfidence, especially when the
text is short, poetic, non-native English, or stylistically unusual.

Submitted text:
"""
{clipped_text}
"""'''.strip()


def run_groq_llm_signal(text: str) -> LlmSignalResult:
    """Run Signal 1: Groq LLM classification.

    Returns an AI-likelihood score where:
    - 0.0 means strongly human-like
    - 0.5 means uncertain/mixed
    - 1.0 means strongly AI-like
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        raise SignalError("Cannot classify empty text.")

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    allow_mock = os.getenv("PROVENANCE_ALLOW_MOCK_SIGNAL", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }

    if not api_key:
        if allow_mock:
            return _mock_llm_signal(cleaned_text)
        raise SignalError("GROQ_API_KEY is missing and mock fallback is disabled.")

    client = Groq(api_key=api_key)

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Return strict JSON only. Do not include markdown.",
                },
                {"role": "user", "content": _build_prompt(cleaned_text)},
            ],
            temperature=0.0,
            max_tokens=350,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # Groq can raise several transport/API exceptions.
        if allow_mock:
            fallback = _mock_llm_signal(cleaned_text)
            return LlmSignalResult(
                signal=fallback.signal,
                ai_score=fallback.ai_score,
                verdict=fallback.verdict,
                rationale=f"Groq call failed; local mock fallback used. Cause: {exc.__class__.__name__}.",
                limitations=fallback.limitations,
                mocked=True,
            )
        raise SignalError(f"Groq LLM signal failed: {exc.__class__.__name__}") from exc

    raw_content = completion.choices[0].message.content or ""
    payload = _extract_json_object(raw_content)
    ai_score = _clamp_score(payload.get("ai_score"))
    verdict = _normalize_verdict(payload.get("verdict"), ai_score)
    rationale = str(payload.get("rationale") or "No rationale provided.").strip()

    raw_limitations = payload.get("limitations")
    if isinstance(raw_limitations, list):
        limitations = [str(item).strip() for item in raw_limitations if str(item).strip()]
    else:
        limitations = ["LLM result is not proof of authorship."]

    return LlmSignalResult(
        signal="groq_llm",
        ai_score=round(ai_score, 3),
        verdict=verdict,
        rationale=rationale[:500],
        limitations=limitations[:3],
        mocked=False,
    )
