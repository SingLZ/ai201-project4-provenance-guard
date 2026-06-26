"""Provenance Guard Flask app - Milestone 3.

Implements:
- POST /submit with Signal 1 wired end-to-end
- GET /log for structured audit-log visibility
- GET /health for simple local checks
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import append_log_entry, get_recent_log_entries, save_content_record, utc_now_iso
from detection_signals import SignalError, run_groq_llm_signal

MAX_TEXT_CHARS = 20_000
SUBMIT_RATE_LIMIT = "10 per minute"


def create_app() -> Flask:
    app = Flask(__name__)

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["100 per hour"],
        storage_uri="memory://",
    )

    @app.get("/health")
    def health() -> tuple[Any, int]:
        return jsonify({"status": "ok", "service": "provenance_guard", "milestone": 3}), 200

    @app.post("/submit")
    @limiter.limit(SUBMIT_RATE_LIMIT)
    def submit() -> tuple[Any, int]:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400

        text = payload.get("text")
        creator_id = payload.get("creator_id")
        title = payload.get("title")
        content_type = payload.get("content_type", "text")

        validation_error = _validate_submit_payload(text, creator_id, title, content_type)
        if validation_error is not None:
            return jsonify({"error": validation_error}), 400

        cleaned_text = text.strip()
        content_id = str(uuid4())

        try:
            llm_result = run_groq_llm_signal(cleaned_text)
        except SignalError as exc:
            append_log_entry(
                {
                    "event_type": "classification_failed",
                    "content_id": content_id,
                    "creator_id": creator_id.strip(),
                    "error": str(exc),
                    "status": "failed",
                }
            )
            return jsonify({"error": str(exc), "content_id": content_id}), 502

        # Milestone 3 placeholder: final multi-signal confidence is built in M4.
        placeholder_confidence = llm_result.ai_score
        attribution = _attribution_from_signal_score(llm_result.ai_score)
        label = "Placeholder label: final transparency labels will be implemented in Milestone 5."

        response_body = {
            "content_id": content_id,
            "creator_id": creator_id.strip(),
            "attribution": attribution,
            "confidence": placeholder_confidence,
            "label": label,
            "status": "classified",
            "signals": {
                "groq_llm": llm_result.to_dict(),
            },
        }

        save_content_record(
            content_id,
            {
                "content_id": content_id,
                "creator_id": creator_id.strip(),
                "title": title.strip() if isinstance(title, str) and title.strip() else None,
                "content_type": "text",
                "text_sha256": hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest(),
                "text_excerpt": cleaned_text[:240],
                "created_at": utc_now_iso(),
                "attribution": attribution,
                "confidence": placeholder_confidence,
                "llm_score": llm_result.ai_score,
                "status": "classified",
            },
        )

        append_log_entry(
            {
                "event_type": "classification_decision",
                "content_id": content_id,
                "creator_id": creator_id.strip(),
                "attribution": attribution,
                "confidence": placeholder_confidence,
                "llm_score": llm_result.ai_score,
                "llm_verdict": llm_result.verdict,
                "llm_mocked": llm_result.mocked,
                "status": "classified",
            }
        )

        return jsonify(response_body), 201

    @app.get("/log")
    def log() -> tuple[Any, int]:
        raw_limit = request.args.get("limit", "20")
        try:
            limit = int(raw_limit)
        except ValueError:
            return jsonify({"error": "limit must be an integer."}), 400
        limit = max(1, min(100, limit))
        return jsonify({"entries": get_recent_log_entries(limit=limit)}), 200

    return app


def _validate_submit_payload(
    text: Any,
    creator_id: Any,
    title: Any,
    content_type: Any,
) -> str | None:
    if not isinstance(creator_id, str) or not creator_id.strip():
        return "creator_id is required and must be a non-empty string."
    if not isinstance(text, str) or not text.strip():
        return "text is required and must be a non-empty string."
    if len(text) > MAX_TEXT_CHARS:
        return f"text must be {MAX_TEXT_CHARS} characters or fewer."
    if content_type != "text":
        return "Only content_type='text' is supported in Milestone 3."
    if title is not None and not isinstance(title, str):
        return "title must be a string when provided."
    return None


def _attribution_from_signal_score(ai_score: float) -> str:
    if ai_score >= 0.85:
        return "likely_ai"
    if ai_score <= 0.15:
        return "likely_human"
    return "uncertain"


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
