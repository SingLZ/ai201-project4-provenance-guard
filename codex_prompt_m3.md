# Codex Prompt for Milestone 3

Reasoning level: medium.

You are implementing Milestone 3 for a Flask backend project called Provenance Guard. Use the planning.md Architecture and Detection Signals sections as the source of truth.

## Spec sections to use

- `## Architecture`
- `## Detection Signals`, especially `Signal 1: Groq LLM Classification`
- API contract from Milestone 1 / Milestone 2:
  - `POST /submit`
  - `GET /log`
  - optional `GET /health`

## Generate

1. A Flask app skeleton.
2. A `POST /submit` endpoint that accepts JSON with at least:
   - `text`
   - `creator_id`
3. The first detection signal function using Groq `llama-3.3-70b-versatile`.
4. A structured JSONL audit log that records each submission.
5. A `GET /log` endpoint that returns recent entries.
6. A small direct-signal test script.

## Constraints

- Do not implement Signal 2 yet.
- Do not implement final confidence calibration yet.
- Do not implement appeals yet.
- Use a unique `content_id` for each submission.
- Keep audit entries structured; do not use print statements as the audit log.
- Never commit `.env`.

## Verification

- Run the direct signal script with a few inputs.
- Start Flask and test `POST /submit` using curl.
- Confirm response includes `content_id`, `attribution`, `confidence`, and `label`.
- Call `GET /log` and confirm the latest entries include timestamp, content ID, creator ID, attribution, confidence, and Signal 1 score.
