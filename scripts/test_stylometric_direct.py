"""Direct Signal 2 check for Milestone 4.

Run:
    python scripts/test_stylometric_direct.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection_signals import run_stylometric_signal  # noqa: E402

SAMPLES = {
    "clearly_ai": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.",
    "clearly_human": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there",
    "formal_human_borderline": "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.",
    "edited_ai_borderline": "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type.",
}


def main() -> None:
    for name, text in SAMPLES.items():
        result = run_stylometric_signal(text)
        print(f"\n--- {name} ---")
        print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
