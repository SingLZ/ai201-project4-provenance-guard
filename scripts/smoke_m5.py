"""Milestone 5 smoke test.

This test uses deterministic signal fakes so it can verify production-layer behavior
without spending Groq quota or depending on model variability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import app as app_module  # noqa: E402
from detection_signals import LlmSignalResult, StylometricSignalResult  # noqa: E402


def _score_for_text(text: str) -> float:
    if "force-high-ai" in text:
        return 0.95
    if "force-high-human" in text:
        return 0.05
    return 0.60


def fake_llm_signal(text: str) -> LlmSignalResult:
    score = _score_for_text(text)
    verdict = "ai" if score >= 0.85 else "human" if score <= 0.20 else "uncertain"
    return LlmSignalResult(
        signal="groq_llm",
        ai_score=score,
        verdict=verdict,  # type: ignore[arg-type]
        rationale="Deterministic smoke-test LLM signal.",
        limitations=["Smoke-test fake; not a real LLM result."],
        mocked=True,
    )


def fake_stylometric_signal(text: str) -> StylometricSignalResult:
    score = _score_for_text(text)
    return StylometricSignalResult(
        signal="stylometric_heuristics",
        ai_score=score,
        metrics={
            "word_count": 120,
            "sentence_count": 8,
            "sentence_length_variance": 12.0,
            "type_token_ratio": 0.70,
            "punctuation_density": 0.08,
            "repetition_ratio": 0.02,
            "transition_phrase_density": 0.01,
            "average_word_length": 4.8,
        },
        rationale="Deterministic smoke-test stylometric signal.",
        limitations=["Smoke-test fake; not a real stylometric measurement."],
    )


def post_submit(client, marker: str, creator_id: str):
    response = client.post(
        "/submit",
        json={
            "creator_id": creator_id,
            "text": f"This smoke-test input contains {marker} and enough words are simulated by fake metrics.",
        },
    )
    if response.status_code != 200:
        raise AssertionError(f"/submit failed: {response.status_code} {response.get_data(as_text=True)}")
    return response.get_json()


def main() -> None:
    app_module.run_groq_llm_signal = fake_llm_signal
    app_module.run_stylometric_signal = fake_stylometric_signal

    flask_app = app_module.create_app()
    flask_app.testing = True
    client = flask_app.test_client()

    high_ai = post_submit(client, "force-high-ai", "m5-ai-user")
    uncertain = post_submit(client, "force-uncertain", "m5-uncertain-user")
    high_human = post_submit(client, "force-high-human", "m5-human-user")

    expected = [
        (high_ai, "high_confidence_ai"),
        (uncertain, "uncertain"),
        (high_human, "high_confidence_human"),
    ]
    for payload, expected_result in expected:
        actual = payload.get("attribution_result")
        if actual != expected_result:
            raise AssertionError(f"expected {expected_result}, got {actual}: {payload}")
        if "Provenance Guard" not in str(payload.get("transparency_label", "")):
            raise AssertionError(f"missing label text: {payload}")
        if len(payload.get("signals", [])) != 2:
            raise AssertionError(f"expected two signals: {payload}")

    appeal_response = client.post(
        "/appeal",
        json={
            "content_id": high_ai["content_id"],
            "creator_id": "m5-ai-user",
            "creator_reasoning": "I wrote this myself from personal experience and want a human review.",
        },
    )
    if appeal_response.status_code != 200:
        raise AssertionError(f"/appeal failed: {appeal_response.status_code} {appeal_response.get_data(as_text=True)}")
    appeal_payload = appeal_response.get_json()
    if appeal_payload.get("status") != "under_review":
        raise AssertionError(f"appeal did not set under_review: {appeal_payload}")

    content_response = client.get(f"/content/{high_ai['content_id']}")
    content_payload = content_response.get_json()
    if content_payload.get("status") != "under_review" or content_payload.get("appeal_filed") is not True:
        raise AssertionError(f"content status was not updated: {content_payload}")

    appeals_payload = client.get("/appeals?limit=5").get_json()
    if not appeals_payload.get("appeals"):
        raise AssertionError("appeal queue is empty")

    log_payload = client.get("/log?limit=10").get_json()
    events = [entry.get("event_type") for entry in log_payload.get("entries", [])]
    if "classification_decision" not in events or "appeal_created" not in events or "status_updated" not in events:
        raise AssertionError(f"missing audit events: {json.dumps(log_payload, indent=2)}")

    # Separate app instance to avoid consuming the same submit limit used above.
    rate_app = app_module.create_app()
    rate_app.testing = True
    rate_client = rate_app.test_client()
    status_codes = []
    for index in range(12):
        response = rate_client.post(
            "/submit",
            json={"creator_id": "ratelimit-test", "text": f"rate limit force-uncertain test {index}"},
        )
        status_codes.append(response.status_code)
    if 429 not in status_codes:
        raise AssertionError(f"expected at least one 429 from rate limit, got {status_codes}")

    print("--- label variants ---")
    print(json.dumps(
        {
            "high_ai": high_ai["attribution_result"],
            "uncertain": uncertain["attribution_result"],
            "high_human": high_human["attribution_result"],
        },
        indent=2,
    ))
    print("--- appeal response ---")
    print(json.dumps(appeal_payload, indent=2))
    print("--- rate-limit status codes ---")
    print(status_codes)
    print("--- recent audit events ---")
    print(json.dumps(log_payload, indent=2))
    print("PASS: Milestone 5 production layer is working.")


if __name__ == "__main__":
    main()
