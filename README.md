# Provenance Guard

Provenance Guard is a Flask backend for text attribution transparency. It accepts a piece of text, runs a multi-signal detection pipeline, returns a calibrated confidence score, displays a transparency label, supports creator appeals, rate-limits submissions, and writes structured audit logs.

## Features Implemented

- `POST /submit`: accepts text and returns attribution result, confidence score, transparency label, and both signal outputs.
- Signal 1: Groq LLM classification using `llama-3.3-70b-versatile`.
- Signal 2: deterministic stylometric heuristics.
- Multi-signal confidence scoring.
- Three transparency label variants.
- `POST /appeal`: creator appeal workflow.
- `GET /content/<content_id>`: content status lookup.
- `GET /appeals`: reviewer queue.
- `GET /log`: structured JSONL audit-log output.
- Flask-Limiter rate limiting.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
GROQ_API_KEY=your_key_here
```

Run:

```bash
python app.py
```

## API

### `POST /submit`

Request:

```json
{
  "creator_id": "creator_123",
  "text": "The submitted poem, story excerpt, or blog post goes here.",
  "title": "Optional title",
  "content_type": "text"
}
```

Response:

```json
{
  "content_id": "uuid",
  "creator_id": "creator_123",
  "status": "classified",
  "attribution_result": "uncertain",
  "ai_likelihood": 0.6,
  "confidence_score": 0.6,
  "transparency_label": "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made.",
  "signals": [
    {"signal": "groq_llm", "ai_score": 0.67},
    {"signal": "stylometric_heuristics", "ai_score": 0.51}
  ]
}
```

### `POST /appeal`

Request:

```json
{
  "content_id": "uuid",
  "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."
}
```

Optional fields:

```json
{
  "creator_id": "creator_123",
  "evidence_summary": "I can provide earlier drafts and an outline."
}
```

Response:

```json
{
  "appeal_id": "uuid",
  "content_id": "uuid",
  "status": "under_review",
  "message": "Appeal received. The original classification has been marked for review."
}
```

### Other Endpoints

- `GET /health`
- `GET /content/<content_id>`
- `GET /appeals?limit=20`
- `GET /log?limit=20`

## Confidence Score Semantics

`confidence_score` is an AI-likelihood score:

| Score Range | Attribution Result | Meaning |
|---:|---|---|
| `0.00 - 0.20` | `high_confidence_human` | Strong human-like evidence |
| `0.21 - 0.84` | `uncertain` | Not strong enough either way |
| `0.85 - 1.00` | `high_confidence_ai` | Strong AI-like evidence |

The AI threshold is intentionally high to reduce false positives against human creators.

## Transparency Label Variants

| Variant | Exact Label Text |
|---|---|
| `high_confidence_ai` | "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship." |
| `high_confidence_human` | "Provenance Guard found strong signs that this text was likely written by a human. This label is based on multiple detection signals and does not prove authorship." |
| `uncertain` | "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made." |

## Rate Limiting

| Endpoint | Limit | Reasoning |
|---|---:|---|
| `POST /submit` | `10 per minute` per IP | Allows normal creator use while blocking rapid spam. |
| `POST /submit` | `100 per day` per IP | Protects the free Groq tier from bulk abuse. |
| `POST /appeal` | `20 per day` per IP | Appeals should be rare and should not be spammed. |
| `GET /log` | `60 per minute` per IP | Enough for grading/debugging without unlimited polling. |

Flask-Limiter uses local memory storage for this course project:

```python
Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
```

Rate-limit evidence from `scripts/smoke_m5.py`:

```text
[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429]
```

## Audit Log

Audit logs are structured JSONL files in `data/audit_log.jsonl`. The `data/` directory is ignored by Git, so paste sample output into the README or grading notes when needed.

Each classification decision logs:

- timestamp
- content ID
- creator ID
- attribution result
- AI likelihood
- confidence score
- transparency label
- both signal scores
- stylometric metrics
- calibration notes
- appeal status

Each appeal logs:

- appeal ID
- content ID
- creator reasoning
- original classification result
- original confidence score
- status update to `under_review`

Sample structured audit entries:

```json
[
  {
    "event_type": "classification_decision",
    "content_id": "content_001",
    "status": "classified",
    "appeal_filed": false,
    "attribution_result": "high_confidence_ai",
    "confidence_score": 0.95,
    "signal_scores": {
      "groq_llm": 0.95,
      "stylometric_heuristics": 0.95
    },
    "transparency_label": "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship."
  },
  {
    "event_type": "appeal_created",
    "appeal_id": "appeal_001",
    "content_id": "content_001",
    "status": "under_review",
    "appeal_filed": true,
    "appeal_reasoning": "I wrote this myself from personal experience and want a human review."
  },
  {
    "event_type": "status_updated",
    "content_id": "content_001",
    "old_status": "classified",
    "new_status": "under_review",
    "reason": "creator_appeal_received"
  }
]
```

## Tests

```bash
python -m compileall .
python scripts/test_labels_direct.py
python scripts/test_stylometric_direct.py
python scripts/smoke_m4.py
python scripts/smoke_m5.py
```

`smoke_m5.py` uses deterministic fake signal functions so it can verify all three labels and rate limiting without consuming Groq quota.
