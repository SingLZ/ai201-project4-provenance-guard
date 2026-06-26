"""Direct Signal 1 check for Milestone 3.

Run:
    python scripts/test_signal_direct.py

Set GROQ_API_KEY in .env to use the real Groq signal. Without a key, the
explicit mock fallback is used so you can still inspect the output shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection_signals import run_groq_llm_signal  # noqa: E402

SAMPLES = [
    "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.",
    "In conclusion, it is important to note that creative expression serves as a profound tapestry of human emotion, enabling individuals to explore diverse perspectives.",
    "Rain. Rain again. The bus coughs. My sleeve smells like pennies.",
]


def main() -> None:
    for index, sample in enumerate(SAMPLES, start=1):
        result = run_groq_llm_signal(sample)
        print(f"\n--- sample {index} ---")
        print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
