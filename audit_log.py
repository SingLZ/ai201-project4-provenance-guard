"""Structured JSONL audit logging and JSON content storage for Provenance Guard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.jsonl"
_CONTENT_STORE_PATH = DATA_DIR / "content_store.json"
_APPEAL_STORE_PATH = DATA_DIR / "appeals_store.json"
_LOCK = Lock()


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp compatible with Python 3.10+."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def append_log_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one structured audit entry and return the persisted entry."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    persisted = {"timestamp": utc_now_iso(), **entry}
    with _LOCK:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(persisted, ensure_ascii=False, sort_keys=True) + "\n")
    return persisted


def get_recent_log_entries(limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent audit log entries, oldest-to-newest."""
    if limit <= 0:
        return []
    if not AUDIT_LOG_PATH.exists():
        return []

    with _LOCK:
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()

    selected = lines[-limit:]
    entries: list[dict[str, Any]] = []
    for line in selected:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_json_object(path: Path, payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def save_content_record(content_id: str, record: dict[str, Any]) -> None:
    """Persist minimal content metadata for content lookup and appeals."""
    with _LOCK:
        store = _read_json_object(_CONTENT_STORE_PATH)
        store[content_id] = record
        _write_json_object(_CONTENT_STORE_PATH, store)


def get_content_record(content_id: str) -> dict[str, Any] | None:
    with _LOCK:
        store = _read_json_object(_CONTENT_STORE_PATH)
    record = store.get(content_id)
    return record if isinstance(record, dict) else None


def update_content_record(content_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update a content record and return the updated value, or None if missing."""
    with _LOCK:
        store = _read_json_object(_CONTENT_STORE_PATH)
        record = store.get(content_id)
        if not isinstance(record, dict):
            return None
        updated = {**record, **updates}
        store[content_id] = updated
        _write_json_object(_CONTENT_STORE_PATH, store)
    return updated


def save_appeal_record(appeal_id: str, record: dict[str, Any]) -> None:
    """Persist one appeal record for the reviewer queue."""
    with _LOCK:
        store = _read_json_object(_APPEAL_STORE_PATH)
        store[appeal_id] = record
        _write_json_object(_APPEAL_STORE_PATH, store)


def get_recent_appeals(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent appeal records, oldest-to-newest."""
    if limit <= 0:
        return []
    with _LOCK:
        store = _read_json_object(_APPEAL_STORE_PATH)
    appeals = [record for record in store.values() if isinstance(record, dict)]
    appeals.sort(key=lambda item: str(item.get("created_at", "")))
    return appeals[-limit:]
