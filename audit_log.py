"""Structured JSONL audit logging for Provenance Guard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.jsonl"
_CONTENT_STORE_PATH = DATA_DIR / "content_store.json"
_LOCK = Lock()


def utc_now_iso() -> str:
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


def _read_content_store() -> dict[str, Any]:
    if not _CONTENT_STORE_PATH.exists():
        return {}
    try:
        parsed = json.loads(_CONTENT_STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def save_content_record(content_id: str, record: dict[str, Any]) -> None:
    """Persist minimal content metadata for Milestone 5 appeals."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        store = _read_content_store()
        store[content_id] = record
        _CONTENT_STORE_PATH.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")


def get_content_record(content_id: str) -> dict[str, Any] | None:
    store = _read_content_store()
    record = store.get(content_id)
    return record if isinstance(record, dict) else None
