"""Milestone 4 smoke check using Flask's test client.

Run:
    python scripts/smoke_m4.py

Verifies:
- POST /submit returns final planning.md field names.
- Both detection signals are present.
- confidence_score maps through the required threshold function.
- GET /log records individual signal scores and combined score.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from detection_signals import attribution_from_confidence_score  # noqa: E402

SAMPLES = [
    {
        "name": "clearly_ai",
        "creator_id": "m4-test-ai",
        "text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.",
    },
    {
        "name": "clearly_human",
        "creator_id": "m4-test-human",
        "text": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there",
    },
    {
        "name": "formal_human_borderline",
        "creator_id": "m4-test-formal",
        "text": "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.",
    },
    {
        "name": "edited_ai_borderline",
        "creator_id": "m4-test-edited",
        "text": "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type.",
    },
]

REQUIRED_TOP_LEVEL = {
    "content_id",
    "creator_id",
    "status",
    "attribution_result",
    "ai_likelihood",
    "confidence_score",
    "transparency_label",
    "signals",
    "scoring",
}


def _assert_submit_contract(body: dict[str, Any]) -> None:
    missing = REQUIRED_TOP_LEVEL - set(body.keys())
    if missing:
        raise AssertionError(f"Missing top-level response fields: {sorted(missing)}")
    if not isinstance(body["signals"], list) or len(body["signals"]) != 2:
        raise AssertionError("signals must be a list with exactly two signal results")
    signal_names = {signal.get("signal") for signal in body["signals"] if isinstance(signal, dict)}
    if signal_names != {"groq_llm", "stylometric_heuristics"}:
        raise AssertionError(f"Unexpected signal names: {sorted(signal_names)}")
    score = body["confidence_score"]
    if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
        raise AssertionError("confidence_score must be numeric and within [0.0, 1.0]")
    expected_result = attribution_from_confidence_score(float(score))
    if body["attribution_result"] != expected_result:
        raise AssertionError(
            f"attribution_result {body['attribution_result']!r} does not match threshold result {expected_result!r}"
        )


def main() -> None:
    # Verify the three threshold categories directly.
    threshold_checks = {
        0.05: "high_confidence_human",
        0.60: "uncertain",
        0.95: "high_confidence_ai",
    }
    for score, expected in threshold_checks.items():
        actual = attribution_from_confidence_score(score)
        if actual != expected:
            raise AssertionError(f"score {score} mapped to {actual}, expected {expected}")

    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    print("--- submit responses ---")
    for sample in SAMPLES:
        response = client.post(
            "/submit",
            json={"creator_id": sample["creator_id"], "text": sample["text"]},
        )
        if response.status_code != 200:
            raise RuntimeError(f"/submit failed: {response.status_code} {response.get_data(as_text=True)}")
        body = response.get_json()
        _assert_submit_contract(body)
        print(f"\n[{sample['name']}]")
        print(json.dumps(body, indent=2))

    log_response = client.get("/log?limit=4")
    if log_response.status_code != 200:
        raise RuntimeError(f"/log failed: {log_response.status_code} {log_response.get_data(as_text=True)}")
    log_body = log_response.get_json()
    entries = log_body.get("entries", [])
    if len(entries) < 4:
        raise AssertionError("Expected at least four recent audit entries")

    for entry in entries:
        for required in ("signal_scores", "llm_score", "stylometric_score", "confidence_score"):
            if required not in entry:
                raise AssertionError(f"Audit entry missing {required}: {entry}")

    print("\n--- recent audit entries ---")
    print(json.dumps(log_body, indent=2))
    print("\nPASS: Milestone 4 multi-signal contract is working.")


if __name__ == "__main__":
    main()
