"""Detection and scoring logic for Provenance Guard.

Milestone 4 implements:
- Signal 1: Groq LLM classification.
- Signal 2: deterministic stylometric heuristics.
- Multi-signal confidence scoring and label selection.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from dotenv import load_dotenv
try:
    from groq import Groq
except ModuleNotFoundError:  # Allows pure stylometric tests before dependencies are installed.
    Groq = None  # type: ignore[assignment]

load_dotenv()

Verdict = Literal["human", "ai", "uncertain"]
AttributionResult = Literal["high_confidence_human", "uncertain", "high_confidence_ai"]

HIGH_CONFIDENCE_AI_LABEL = (
    "Provenance Guard found strong signs that this text may have been AI-generated. "
    "This label is based on multiple detection signals and is not a final judgment of authorship."
)
HIGH_CONFIDENCE_HUMAN_LABEL = (
    "Provenance Guard found strong signs that this text was likely written by a human. "
    "This label is based on multiple detection signals and does not prove authorship."
)
UNCERTAIN_LABEL = (
    "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. "
    "The result is uncertain, so no strong attribution claim is being made."
)


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


@dataclass(frozen=True)
class StylometricSignalResult:
    signal: str
    ai_score: float
    metrics: dict[str, int | float]
    rationale: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfidenceResult:
    ai_likelihood: float
    confidence_score: float
    attribution_result: AttributionResult
    transparency_label: str
    raw_combined_score: float
    calibration_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SignalError(RuntimeError):
    """Raised when a detection signal cannot produce a valid result."""


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise SignalError("LLM response did not include a numeric ai_score.") from exc
    return clamp(score)


def _normalize_verdict(value: Any, ai_score: float) -> Verdict:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"human", "ai", "uncertain"}:
            return normalized  # type: ignore[return-value]

    if ai_score >= 0.85:
        return "ai"
    if ai_score <= 0.20:
        return "human"
    return "uncertain"


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from the model response."""
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
    """Explicit local fallback for route/audit-log testing without a Groq key."""
    lowered = text.lower()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ai_markers = (
        "as an ai",
        "in conclusion",
        "it is important to note",
        "moreover",
        "furthermore",
        "therefore",
        "transformative paradigm shift",
        "ethical implications",
        "stakeholders",
        "delve",
        "tapestry",
    )
    human_markers = (
        " i ",
        " my ",
        " me ",
        "honestly",
        "ok so",
        "way too",
        "probably won't",
        "coffee",
        "porch",
        "yesterday",
        "mom",
        "dad",
    )

    padded = f" {lowered} "
    marker_score = sum(1 for marker in ai_markers if marker in padded) * 0.10
    personal_score = sum(1 for marker in human_markers if marker in padded) * -0.07
    length_adjustment = 0.06 if len(text.split()) < 40 else 0.0
    hash_noise = (int(text_hash[:2], 16) / 255.0 - 0.5) * 0.03
    score = clamp(0.5 + marker_score + personal_score + length_adjustment + hash_noise, 0.05, 0.95)

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

Use the full 0.00 to 1.00 range when evidence is strong. Assign 0.85 or higher
only when there are multiple strong AI-like indicators such as formulaic framing,
generic balanced structure, low-risk phrasing, and repeated stock transitions.
Assign 0.20 or lower only when there are strong human-like indicators such as
specific personal voice, uneven rhythm, colloquial phrasing, or idiosyncratic detail.
Do not claim proof of authorship. Penalize overconfidence, especially when the
text is short, poetic, non-native English, or stylistically unusual.

Submitted text:
"""
{clipped_text}
"""'''.strip()


def run_groq_llm_signal(text: str) -> LlmSignalResult:
    """Run Signal 1: Groq LLM classification."""
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

    if Groq is None:
        if allow_mock:
            fallback = _mock_llm_signal(cleaned_text)
            return LlmSignalResult(
                signal=fallback.signal,
                ai_score=fallback.ai_score,
                verdict=fallback.verdict,
                rationale="Groq package is not installed; local mock fallback used.",
                limitations=fallback.limitations,
                mocked=True,
            )
        raise SignalError("groq package is not installed and mock fallback is disabled.")

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


_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*")
_PUNCT_RE = re.compile(r"[.!?,;:—\-]")
_TRANSITION_PHRASES = (
    "in conclusion",
    "it is important to note",
    "furthermore",
    "moreover",
    "therefore",
    "as a result",
    "in addition",
    "on the other hand",
    "various sectors",
    "ethical implications",
    "responsible deployment",
    "transformative paradigm shift",
)
_FORMULAIC_TERMS = {
    "artificial",
    "intelligence",
    "transformative",
    "paradigm",
    "modern",
    "society",
    "benefits",
    "numerous",
    "essential",
    "ethical",
    "implications",
    "stakeholders",
    "sectors",
    "collaborate",
    "ensure",
    "responsible",
    "deployment",
    "relationship",
    "policy",
    "fundamental",
    "consequences",
}


def _words(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(text)]


def _sentences(text: str) -> list[str]:
    return [segment.strip() for segment in _SENTENCE_RE.findall(text) if segment.strip()]


def _variance(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _repetition_ratio(tokens: list[str]) -> float:
    if not tokens:
        return 0.0

    word_counts = Counter(tokens)
    repeated_word_count = sum(count - 1 for count in word_counts.values() if count > 1)
    word_repeat_ratio = repeated_word_count / len(tokens)

    if len(tokens) < 6:
        return round(word_repeat_ratio, 4)

    trigrams = [tuple(tokens[index : index + 3]) for index in range(len(tokens) - 2)]
    trigram_counts = Counter(trigrams)
    repeated_trigram_count = sum(count - 1 for count in trigram_counts.values() if count > 1)
    trigram_repeat_ratio = repeated_trigram_count / max(1, len(trigrams))

    return round(clamp((0.65 * word_repeat_ratio) + (0.35 * trigram_repeat_ratio)), 4)


def _transition_phrase_count(lowered_text: str) -> int:
    return sum(lowered_text.count(phrase) for phrase in _TRANSITION_PHRASES)


def _transition_phrase_density(lowered_text: str, word_count: int) -> float:
    if word_count <= 0:
        return 0.0
    return round(_transition_phrase_count(lowered_text) / word_count, 4)


def _formulaic_term_density(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return round(sum(1 for token in tokens if token in _FORMULAIC_TERMS) / len(tokens), 4)


def run_stylometric_signal(text: str) -> StylometricSignalResult:
    """Run Signal 2: deterministic structural writing heuristics.

    Returns an AI-likelihood score where 0.0 is human-like, 0.5 is mixed,
    and 1.0 is AI-like.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        raise SignalError("Cannot analyze empty text.")

    tokens = _words(cleaned_text)
    sentences = _sentences(cleaned_text)
    word_count = len(tokens)
    sentence_count = len(sentences)

    sentence_lengths = [len(_words(sentence)) for sentence in sentences if _words(sentence)]
    sentence_length_variance = round(_variance(sentence_lengths), 3)
    type_token_ratio = round(len(set(tokens)) / word_count, 4) if word_count else 0.0
    punctuation_density = round(len(_PUNCT_RE.findall(cleaned_text)) / word_count, 4) if word_count else 0.0
    repetition_ratio = _repetition_ratio(tokens)
    lowered_text = cleaned_text.lower()
    transition_phrase_count = _transition_phrase_count(lowered_text)
    transition_phrase_density = _transition_phrase_density(lowered_text, word_count)
    formulaic_term_density = _formulaic_term_density(tokens)
    average_word_length = round(sum(len(token) for token in tokens) / word_count, 3) if word_count else 0.0

    # Planned formula from planning.md:
    # 0.30 sentence uniformity + 0.25 vocabulary repetition
    # + 0.20 phrase repetition + 0.15 punctuation pattern + 0.10 transition phrases.
    sentence_uniformity_score = 1.0 - clamp((sentence_length_variance - 4.0) / 60.0)
    limited_vocabulary_score = 1.0 - clamp((type_token_ratio - 0.45) / 0.35)
    formulaic_vocabulary_score = clamp(formulaic_term_density * 8.0)
    vocabulary_repetition_score = max(limited_vocabulary_score, formulaic_vocabulary_score)
    phrase_repetition_score = max(clamp(repetition_ratio * 3.5), clamp(transition_phrase_count / 3.0))
    punctuation_pattern_score = 1.0 - clamp(abs(punctuation_density - 0.075) / 0.11)
    transition_phrase_score = clamp(transition_phrase_density * 25.0)

    ai_score = clamp(
        (0.30 * sentence_uniformity_score)
        + (0.25 * vocabulary_repetition_score)
        + (0.20 * phrase_repetition_score)
        + (0.15 * punctuation_pattern_score)
        + (0.10 * transition_phrase_score)
    )

    metrics: dict[str, int | float] = {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "sentence_length_variance": sentence_length_variance,
        "type_token_ratio": type_token_ratio,
        "punctuation_density": punctuation_density,
        "repetition_ratio": repetition_ratio,
        "transition_phrase_density": transition_phrase_density,
        "formulaic_term_density": formulaic_term_density,
        "average_word_length": average_word_length,
    }

    rationale_parts: list[str] = []
    if sentence_uniformity_score >= 0.7:
        rationale_parts.append("sentence lengths are relatively uniform")
    if vocabulary_repetition_score >= 0.6:
        if formulaic_vocabulary_score >= limited_vocabulary_score:
            rationale_parts.append("formulaic abstract vocabulary is elevated")
        else:
            rationale_parts.append("vocabulary diversity is limited")
    if phrase_repetition_score >= 0.4:
        if transition_phrase_count > 0:
            rationale_parts.append("stock phrases are present")
        else:
            rationale_parts.append("repetition is elevated")
    if transition_phrase_score >= 0.4:
        rationale_parts.append("formulaic transition phrases are present")
    if not rationale_parts:
        rationale_parts.append("metrics are mixed and do not strongly support an AI-like structural pattern")

    limitations = [
        "Stylometric metrics cannot prove authorship.",
        "Short, poetic, or intentionally repetitive writing can distort this signal.",
    ]
    if word_count < 80:
        limitations.append("Text has fewer than 80 words, so the structural score is less stable.")

    return StylometricSignalResult(
        signal="stylometric_heuristics",
        ai_score=round(ai_score, 3),
        metrics=metrics,
        rationale="; ".join(rationale_parts) + ".",
        limitations=limitations,
    )


def attribution_from_confidence_score(score: float) -> AttributionResult:
    bounded = clamp(score)
    if bounded <= 0.20:
        return "high_confidence_human"
    if bounded >= 0.85:
        return "high_confidence_ai"
    return "uncertain"


def transparency_label_for_result(result: AttributionResult) -> str:
    labels: dict[AttributionResult, str] = {
        "high_confidence_ai": HIGH_CONFIDENCE_AI_LABEL,
        "high_confidence_human": HIGH_CONFIDENCE_HUMAN_LABEL,
        "uncertain": UNCERTAIN_LABEL,
    }
    return labels[result]


def combine_signal_scores(
    llm_result: LlmSignalResult,
    stylometric_result: StylometricSignalResult,
) -> ConfidenceResult:
    """Combine Signal 1 and Signal 2 according to planning.md."""
    raw_combined_score = clamp((0.55 * llm_result.ai_score) + (0.45 * stylometric_result.ai_score))
    final_score = raw_combined_score
    notes: list[str] = ["weighted_average: 0.55*groq_llm + 0.45*stylometric_heuristics"]

    if abs(llm_result.ai_score - stylometric_result.ai_score) >= 0.35:
        final_score = 0.5 + ((raw_combined_score - 0.5) * 0.80)
        notes.append("signal_disagreement_calibration_applied")

    word_count = int(stylometric_result.metrics.get("word_count", 0))
    if word_count < 80:
        final_score = 0.5 + ((final_score - 0.5) * 0.70)
        notes.append("short_text_calibration_applied")

    final_score = round(clamp(final_score), 3)
    attribution_result = attribution_from_confidence_score(final_score)

    return ConfidenceResult(
        ai_likelihood=final_score,
        confidence_score=final_score,
        attribution_result=attribution_result,
        transparency_label=transparency_label_for_result(attribution_result),
        raw_combined_score=round(raw_combined_score, 3),
        calibration_notes=notes,
    )
