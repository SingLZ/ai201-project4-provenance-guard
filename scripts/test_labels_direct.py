"""Direct checks for Milestone 5 transparency-label thresholds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from detection_signals import attribution_from_confidence_score, transparency_label_for_result  # noqa: E402

CASES = [
    (0.05, "high_confidence_human"),
    (0.60, "uncertain"),
    (0.95, "high_confidence_ai"),
]


def main() -> None:
    results = []
    for score, expected in CASES:
        result = attribution_from_confidence_score(score)
        label = transparency_label_for_result(result)
        if result != expected:
            raise AssertionError(f"score {score} expected {expected}, got {result}")
        if not label or "Provenance Guard" not in label:
            raise AssertionError(f"score {score} returned invalid label text: {label!r}")
        results.append({"score": score, "result": result, "label": label})

    print(json.dumps(results, indent=2))
    print("PASS: all three transparency label variants are reachable by threshold.")


if __name__ == "__main__":
    main()
