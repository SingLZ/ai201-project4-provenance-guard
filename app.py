"""Provenance Guard Flask app.

Milestone 5 implements the production layer:
- POST /submit with two detection signals, confidence scoring, and final labels.
- POST /appeal with status updates and appeal audit events.
- GET /content/<content_id>, GET /appeals, GET /log, and GET /health.
- Flask-Limiter protection on production-facing endpoints.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import (
    append_log_entry,
    get_content_record,
    get_recent_appeals,
    get_recent_log_entries,
    save_appeal_record,
    save_content_record,
    update_content_record,
    utc_now_iso,
)
from detection_signals import (
    SignalError,
    combine_signal_scores,
    run_groq_llm_signal,
    run_stylometric_signal,
)

MAX_TEXT_CHARS = 20_000
MAX_REASONING_CHARS = 2_000
SUBMIT_RATE_LIMIT = "10 per minute;100 per day"
APPEAL_RATE_LIMIT = "20 per day"
LOG_RATE_LIMIT = "60 per minute"


def create_app() -> Flask:
    app = Flask(__name__)

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )

    @app.errorhandler(429)
    def rate_limit_exceeded(error: Any) -> tuple[Any, int]:
        return (
            jsonify(
                {
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please wait before trying again.",
                }
            ),
            429,
        )

    @app.get("/")
    def index() -> tuple[Any, int]:
        return (
            jsonify(
                {
                    "service": "provenance_guard",
                    "status": "running",
                    "milestone": 5,
                    "routes": ["/health", "/submit", "/appeal", "/content/<content_id>", "/appeals", "/log"],
                }
            ),
            200,
        )

    @app.get("/health")
    def health() -> tuple[Any, int]:
        return jsonify({"status": "ok", "service": "provenance_guard", "milestone": 5}), 200

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
        cleaned_creator_id = creator_id.strip()
        content_id = str(uuid4())

        try:
            llm_result = run_groq_llm_signal(cleaned_text)
            stylometric_result = run_stylometric_signal(cleaned_text)
            confidence_result = combine_signal_scores(llm_result, stylometric_result)
        except SignalError as exc:
            append_log_entry(
                {
                    "event_type": "classification_failed",
                    "content_id": content_id,
                    "creator_id": cleaned_creator_id,
                    "error": str(exc),
                    "status": "failed",
                }
            )
            return jsonify({"error": str(exc), "content_id": content_id}), 502

        signals = [llm_result.to_dict(), stylometric_result.to_dict()]
        response_body = {
            "content_id": content_id,
            "creator_id": cleaned_creator_id,
            "status": "classified",
            "attribution_result": confidence_result.attribution_result,
            "ai_likelihood": confidence_result.ai_likelihood,
            "confidence_score": confidence_result.confidence_score,
            "transparency_label": confidence_result.transparency_label,
            "signals": signals,
            "scoring": {
                "raw_combined_score": confidence_result.raw_combined_score,
                "calibration_notes": confidence_result.calibration_notes,
            },
        }

        created_at = utc_now_iso()
        content_record = {
            "content_id": content_id,
            "creator_id": cleaned_creator_id,
            "title": title.strip() if isinstance(title, str) and title.strip() else None,
            "content_type": "text",
            "text_sha256": hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest(),
            "text_excerpt": cleaned_text[:300],
            "created_at": created_at,
            "updated_at": created_at,
            "status": "classified",
            "appeal_filed": False,
            "attribution_result": confidence_result.attribution_result,
            "ai_likelihood": confidence_result.ai_likelihood,
            "confidence_score": confidence_result.confidence_score,
            "transparency_label": confidence_result.transparency_label,
            "raw_combined_score": confidence_result.raw_combined_score,
            "calibration_notes": confidence_result.calibration_notes,
            "llm_score": llm_result.ai_score,
            "llm_verdict": llm_result.verdict,
            "llm_mocked": llm_result.mocked,
            "stylometric_score": stylometric_result.ai_score,
            "stylometric_metrics": stylometric_result.metrics,
            "signal_scores": {
                "groq_llm": llm_result.ai_score,
                "stylometric_heuristics": stylometric_result.ai_score,
            },
        }
        save_content_record(content_id, content_record)

        append_log_entry(
            {
                "event_type": "classification_decision",
                "content_id": content_id,
                "creator_id": cleaned_creator_id,
                "status": "classified",
                "appeal_filed": False,
                "attribution_result": confidence_result.attribution_result,
                "ai_likelihood": confidence_result.ai_likelihood,
                "confidence_score": confidence_result.confidence_score,
                "raw_combined_score": confidence_result.raw_combined_score,
                "transparency_label": confidence_result.transparency_label,
                "signals_used": ["groq_llm", "stylometric_heuristics"],
                "signal_scores": {
                    "groq_llm": llm_result.ai_score,
                    "stylometric_heuristics": stylometric_result.ai_score,
                },
                "llm_score": llm_result.ai_score,
                "llm_verdict": llm_result.verdict,
                "llm_mocked": llm_result.mocked,
                "stylometric_score": stylometric_result.ai_score,
                "stylometric_metrics": stylometric_result.metrics,
                "calibration_notes": confidence_result.calibration_notes,
            }
        )

        return jsonify(response_body), 200

    @app.post("/appeal")
    @limiter.limit(APPEAL_RATE_LIMIT)
    def appeal() -> tuple[Any, int]:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400

        content_id = payload.get("content_id")
        creator_id = payload.get("creator_id")
        creator_reasoning = payload.get("creator_reasoning", payload.get("reason"))
        evidence_summary = payload.get("evidence_summary")

        validation_error = _validate_appeal_payload(content_id, creator_id, creator_reasoning, evidence_summary)
        if validation_error is not None:
            return jsonify({"error": validation_error}), 400

        content_record = get_content_record(content_id.strip())
        if content_record is None:
            return jsonify({"error": "content_id was not found."}), 404

        stored_creator_id = str(content_record.get("creator_id", ""))
        if isinstance(creator_id, str) and creator_id.strip() and creator_id.strip() != stored_creator_id:
            return jsonify({"error": "creator_id does not match the original content creator."}), 403

        appeal_id = str(uuid4())
        created_at = utc_now_iso()
        old_status = str(content_record.get("status", "classified"))
        cleaned_reasoning = creator_reasoning.strip()
        cleaned_evidence = evidence_summary.strip() if isinstance(evidence_summary, str) and evidence_summary.strip() else None

        updated_content = update_content_record(
            content_id.strip(),
            {
                "status": "under_review",
                "appeal_filed": True,
                "appeal_id": appeal_id,
                "appeal_reasoning": cleaned_reasoning,
                "updated_at": created_at,
            },
        )
        if updated_content is None:
            return jsonify({"error": "content_id was not found."}), 404

        appeal_record = {
            "appeal_id": appeal_id,
            "content_id": content_id.strip(),
            "creator_id": stored_creator_id,
            "title": content_record.get("title"),
            "content_excerpt": content_record.get("text_excerpt", ""),
            "original_result": content_record.get("attribution_result"),
            "original_confidence_score": content_record.get("confidence_score"),
            "signal_scores": content_record.get("signal_scores", {}),
            "transparency_label": content_record.get("transparency_label"),
            "appeal_reasoning": cleaned_reasoning,
            "evidence_summary": cleaned_evidence,
            "status": "under_review",
            "created_at": created_at,
        }
        save_appeal_record(appeal_id, appeal_record)

        append_log_entry(
            {
                "event_type": "appeal_created",
                "appeal_id": appeal_id,
                "content_id": content_id.strip(),
                "creator_id": stored_creator_id,
                "status": "under_review",
                "appeal_filed": True,
                "appeal_reasoning": cleaned_reasoning,
                "evidence_summary": cleaned_evidence,
                "original_attribution_result": content_record.get("attribution_result"),
                "original_confidence_score": content_record.get("confidence_score"),
                "signal_scores": content_record.get("signal_scores", {}),
            }
        )
        append_log_entry(
            {
                "event_type": "status_updated",
                "content_id": content_id.strip(),
                "creator_id": stored_creator_id,
                "old_status": old_status,
                "new_status": "under_review",
                "status": "under_review",
                "appeal_filed": True,
                "appeal_id": appeal_id,
                "reason": "creator_appeal_received",
            }
        )

        return (
            jsonify(
                {
                    "appeal_id": appeal_id,
                    "content_id": content_id.strip(),
                    "status": "under_review",
                    "message": "Appeal received. The original classification has been marked for review.",
                }
            ),
            200,
        )

    @app.get("/content/<content_id>")
    def content(content_id: str) -> tuple[Any, int]:
        record = get_content_record(content_id)
        if record is None:
            return jsonify({"error": "content_id was not found."}), 404
        return jsonify(record), 200

    @app.get("/appeals")
    def appeals() -> tuple[Any, int]:
        raw_limit = request.args.get("limit", "20")
        limit_or_error = _parse_limit(raw_limit)
        if isinstance(limit_or_error, str):
            return jsonify({"error": limit_or_error}), 400
        return jsonify({"appeals": get_recent_appeals(limit=limit_or_error)}), 200

    @app.get("/log")
    @limiter.limit(LOG_RATE_LIMIT)
    def log() -> tuple[Any, int]:
        raw_limit = request.args.get("limit", "20")
        limit_or_error = _parse_limit(raw_limit)
        if isinstance(limit_or_error, str):
            return jsonify({"error": limit_or_error}), 400
        return jsonify({"entries": get_recent_log_entries(limit=limit_or_error)}), 200

    return app


def _parse_limit(raw_limit: str) -> int | str:
    try:
        limit = int(raw_limit)
    except ValueError:
        return "limit must be an integer."
    return max(1, min(100, limit))


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
        return "Only content_type='text' is supported."
    if title is not None and not isinstance(title, str):
        return "title must be a string when provided."
    return None


def _validate_appeal_payload(
    content_id: Any,
    creator_id: Any,
    creator_reasoning: Any,
    evidence_summary: Any,
) -> str | None:
    if not isinstance(content_id, str) or not content_id.strip():
        return "content_id is required and must be a non-empty string."
    if creator_id is not None and not isinstance(creator_id, str):
        return "creator_id must be a string when provided."
    if not isinstance(creator_reasoning, str) or len(creator_reasoning.strip()) < 10:
        return "creator_reasoning is required and must be at least 10 characters."
    if len(creator_reasoning) > MAX_REASONING_CHARS:
        return f"creator_reasoning must be {MAX_REASONING_CHARS} characters or fewer."
    if evidence_summary is not None and not isinstance(evidence_summary, str):
        return "evidence_summary must be a string when provided."
    if isinstance(evidence_summary, str) and len(evidence_summary) > 1_000:
        return "evidence_summary must be 1000 characters or fewer."
    return None


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
