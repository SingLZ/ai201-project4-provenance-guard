# Codex Prompt — Milestone 5 Production Layer

Reasoning level: medium.

You are working in a Flask project for Provenance Guard. Implement Milestone 5 only. Do not rewrite the project unnecessarily.

Use these spec sections from `planning.md`:

- `## Transparency Label Design`
- `## Appeals Workflow`
- `## API Surface`
- `## Rate Limiting Plan`
- `## Audit Log Plan`
- `## Architecture`

Tasks:

1. Implement final transparency-label mapping:
   - `score <= 0.20` -> `high_confidence_human`
   - `0.21 <= score <= 0.84` -> `uncertain`
   - `score >= 0.85` -> `high_confidence_ai`
   - Use the exact label text from `planning.md`.

2. Implement `POST /appeal`:
   - Accept `content_id` and `creator_reasoning`.
   - Support optional `creator_id` and reject it if it does not match the stored content creator.
   - Update stored content status to `under_review`.
   - Persist an appeal record.
   - Append `appeal_created` and `status_updated` audit events.

3. Implement lookup endpoints:
   - `GET /content/<content_id>`
   - `GET /appeals`
   - Keep `GET /log`.

4. Apply Flask-Limiter:
   - Use `storage_uri="memory://"`.
   - `POST /submit`: `10 per minute;100 per day`
   - `POST /appeal`: `20 per day`
   - `GET /log`: `60 per minute`

5. Keep audit logging structured JSONL. Do not migrate to SQLite.

Validation:

- Run `python -m compileall .`
- Run `python scripts/test_labels_direct.py`
- Run `python scripts/test_stylometric_direct.py`
- Run `python scripts/smoke_m5.py`
- Do not run broad or expensive tests.
