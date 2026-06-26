"""Minimal Milestone 3 smoke check using Flask's test client.

Run:
    python scripts/smoke_m3.py

This avoids starting a server and verifies:
- POST /submit returns required fields
- structured audit entries are written
- GET /log returns entries
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402

SAMPLES = [
    {
        "creator_id": "test-user-1",
        "text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.",
    },
    {
        "creator_id": "test-user-2",
        "text": "In conclusion, it is important to note that technological advancement offers a multifaceted tapestry of opportunities for modern creators.",
    },
    {
        "creator_id": "test-user-3",
        "text": "Rain. Rain again. The bus coughs. My sleeve smells like pennies.",
    },
]


def main() -> None:
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    content_ids: list[str] = []
    for sample in SAMPLES:
        response = client.post("/submit", json=sample)
        if response.status_code != 201:
            raise RuntimeError(f"/submit failed: {response.status_code} {response.get_data(as_text=True)}")
        body = response.get_json()
        content_ids.append(body["content_id"])
        print(json.dumps(body, indent=2))

    log_response = client.get("/log?limit=3")
    if log_response.status_code != 200:
        raise RuntimeError(f"/log failed: {log_response.status_code} {log_response.get_data(as_text=True)}")
    print("\n--- recent audit entries ---")
    print(json.dumps(log_response.get_json(), indent=2))
    print("\nSaved content_id values for Milestone 5 appeals:")
    for content_id in content_ids:
        print(content_id)


if __name__ == "__main__":
    main()
