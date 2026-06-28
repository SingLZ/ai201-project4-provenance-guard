# Provenance Guard

Provenance Guard is a Flask backend for text attribution transparency. It accepts submitted creative text, runs a multi-signal attribution pipeline, returns a confidence-aware transparency label, supports creator appeals, rate-limits the submission endpoint, and records structured audit-log events.

The goal is not to prove authorship. AI detection is probabilistic and imperfect. The system is designed to surface context, communicate uncertainty, and give creators a way to contest a classification.

---

## Architecture Overview

A submitted text moves through the system in this order:

```text
Client / Creative Platform
        |
        | POST /submit
        | {creator_id, text, title?, content_type?}
        v
Flask API Layer
        |
        | validate JSON input
        v
Rate Limiter
        |
        | allow or reject request
        v
Content Store
        |
        | create content_id and initial record
        v
Detection Pipeline
        |
        | raw text
        +-------------------------------+
        |                               |
        v                               v
Groq LLM Signal                 Stylometric Signal
        |                               |
        | llm_ai_score                  | stylometric_ai_score
        | verdict/rationale             | metrics/rationale
        +---------------+---------------+
                        |
                        v
                Confidence Scorer
                        |
                        | weighted combined score
                        | uncertainty calibration
                        v
                Label Generator
                        |
                        | attribution_result
                        | transparency_label
                        v
                Audit Logger
                        |
                        | structured JSONL event
                        v
                API Response
```

Appeals use a separate flow:

```text
Creator
   |
   | POST /appeal
   | {content_id, creator_reasoning, creator_id?, evidence_summary?}
   v
Appeal Handler
   |
   | find original classification
   | save appeal reasoning
   | update content status to under_review
   v
Audit Logger
   |
   | appeal_created event
   | status_updated event
   v
API Response
```

The API response from `/submit` includes the final attribution result, the calibrated confidence score, the user-facing transparency label, and both individual signal outputs.

---

## Implemented Features

- `POST /submit`: accepts text and returns attribution result, confidence score, transparency label, and both signal outputs.
- Signal 1: Groq LLM classification using `llama-3.3-70b-versatile`.
- Signal 2: deterministic stylometric heuristics.
- Multi-signal confidence scoring with uncertainty calibration.
- Three transparency label variants.
- `POST /appeal`: creator appeal workflow.
- `GET /content/<content_id>`: content status lookup.
- `GET /appeals`: reviewer queue.
- `GET /log`: structured JSONL audit-log output.
- Flask-Limiter rate limiting.

---

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

Run the app:

```bash
python app.py
```

Health check:

```bash
curl -s http://127.0.0.1:5000/health | python -m json.tool
```

---

## API Usage

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

Response shape:

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
    {
      "signal": "groq_llm",
      "ai_score": 0.67,
      "verdict": "uncertain",
      "rationale": "The text has some polished structure, but evidence is not strong enough."
    },
    {
      "signal": "stylometric_heuristics",
      "ai_score": 0.51,
      "metrics": {
        "word_count": 220,
        "sentence_count": 14,
        "sentence_length_variance": 8.4,
        "type_token_ratio": 0.61,
        "punctuation_density": 0.08,
        "repetition_ratio": 0.03,
        "transition_phrase_density": 0.01,
        "average_word_length": 4.7
      }
    }
  ]
}
```

Example command:

```bash
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text":"Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.","creator_id":"demo-user"}' | python -m json.tool
```

### `POST /appeal`

Request:

```json
{
  "content_id": "uuid",
  "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.",
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

---

## Detection Signals

### Signal 1: Groq LLM Classification

The first signal asks an LLM to judge whether the text reads more like human writing or AI-generated writing. I chose this signal because it can evaluate broad semantic and stylistic patterns that are hard to capture with simple counters: generic phrasing, over-polished structure, lack of distinctive voice, and unnatural balance.

Output shape:

```json
{
  "signal": "groq_llm",
  "ai_score": 0.85,
  "verdict": "ai",
  "rationale": "The text features formulaic framing and generic balanced structure.",
  "limitations": ["Short text length limits analysis"]
}
```

What it misses:

- A polished human writer can look AI-like.
- Human-edited AI text can look human-like.
- Very short text may not provide enough evidence.
- Non-native English writing or formal academic writing can be misread as AI-like.

### Signal 2: Stylometric Heuristics

The second signal computes measurable writing statistics in pure Python. I chose this signal because it is deterministic, explainable, and independent from the LLM. It measures structural properties such as:

- sentence count
- sentence length variance
- type-token ratio, or vocabulary diversity
- punctuation density
- repetition ratio
- transition phrase density
- formulaic term density
- average word length

This signal is useful because AI-generated text often has smoother pacing, more formulaic phrasing, and more predictable structure. Human writing often has more variation, fragments, abrupt transitions, slang, or uneven rhythm.

Output shape:

```json
{
  "signal": "stylometric_heuristics",
  "ai_score": 0.816,
  "metrics": {
    "word_count": 43,
    "sentence_count": 3,
    "sentence_length_variance": 29.556,
    "type_token_ratio": 0.8837,
    "punctuation_density": 0.1163,
    "repetition_ratio": 0.0756,
    "transition_phrase_density": 0.1395,
    "formulaic_term_density": 0.3953,
    "average_word_length": 6.233
  },
  "rationale": "formulaic abstract vocabulary is elevated; stock phrases are present; formulaic transition phrases are present."
}
```

What it misses:

- Poetry may intentionally repeat words or use simple vocabulary.
- Very short text makes statistics unstable.
- Formulaic human writing can look AI-like.
- Messy or edited AI output can look structurally human.
- Stylometrics cannot understand meaning, intent, humor, sincerity, or cultural context.

---

## Confidence Scoring

The system uses `confidence_score` as an AI-likelihood score:

```text
0.0 = strongest human-like evidence
0.5 = maximum uncertainty or mixed evidence
1.0 = strongest AI-like evidence
```

The two signal scores are combined with a weighted average:

```text
raw_combined_score = (0.55 * groq_llm.ai_score) + (0.45 * stylometric_heuristics.ai_score)
```

The LLM receives slightly more weight because it can evaluate semantics and style. The stylometric signal still receives substantial weight because it is explainable and independent from the LLM.

The scorer then applies uncertainty calibration:

```text
if abs(groq_llm.ai_score - stylometric_heuristics.ai_score) >= 0.35:
    final_score = 0.5 + ((raw_combined_score - 0.5) * 0.80)
else:
    final_score = raw_combined_score

if word_count < 80:
    final_score = 0.5 + ((final_score - 0.5) * 0.70)
```

I added these calibration rules because disagreement between signals and short input length both make the classification less reliable. Instead of forcing a binary answer, the system moves those cases closer to uncertainty.

### Thresholds

| Final `confidence_score` | Attribution Result | Meaning |
|---:|---|---|
| `0.00 - 0.20` | `high_confidence_human` | Strong human-like evidence |
| `0.21 - 0.84` | `uncertain` | Not strong enough either way |
| `0.85 - 1.00` | `high_confidence_ai` | Strong AI-like evidence |

The AI threshold is intentionally high because a false positive can harm a real creator's reputation. Borderline cases return `uncertain` instead of accusing a creator of using AI.

### Example Scores

These examples came from the project smoke tests and show that scores vary by input instead of staying constant.

| Example | Groq Score | Stylometric Score | Final Score | Result | Notes |
|---|---:|---:|---:|---|---|
| High-confidence AI test case | `0.95` | `0.95` | `0.95` | `high_confidence_ai` | Both signals strongly agreed. |
| Clearly human sample | `0.15` | `0.299` | `0.302` | `uncertain` | Human-leaning, but short-text calibration prevented overclaiming. |
| Formal borderline sample | `0.8` | `0.529` | `0.625` | `uncertain` | Formal language looked somewhat AI-like, but not enough for high-confidence AI. |

If I were deploying this for real, I would calibrate these thresholds against a labeled validation set and probably report separate `ai_likelihood` and `decision_confidence` values. For this project, I kept one score because the spec asks for a clear confidence-aware attribution output.

---

## Transparency Label Variants

The backend returns one of these exact label texts in the `transparency_label` field.

| Variant | Exact Label Text |
|---|---|
| `high_confidence_ai` | "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship." |
| `high_confidence_human` | "Provenance Guard found strong signs that this text was likely written by a human. This label is based on multiple detection signals and does not prove authorship." |
| `uncertain` | "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made." |

I tested the label function directly with scores `0.05`, `0.60`, and `0.95`, which produced all three variants.

---

## Appeals Workflow

The appeal workflow lets a creator contest a classification without requiring automated re-classification.

When `POST /appeal` receives a valid `content_id` and `creator_reasoning`, the system:

1. Looks up the original classification record.
2. Saves the appeal reasoning.
3. Updates the content status from `classified` to `under_review`.
4. Logs an `appeal_created` event.
5. Logs a `status_updated` event.
6. Returns the appeal ID and updated status.

Example appeal response:

```json
{
  "appeal_id": "d5d2a335-c65e-452e-84b5-13469e1f107b",
  "content_id": "ab1fdd5c-a8f6-4ec8-9071-3c8db6ab6206",
  "message": "Appeal received. The original classification has been marked for review.",
  "status": "under_review"
}
```

The audit log then records both the appeal and the status change, so a reviewer can see the original classification and the creator's reason for contesting it.

---

## Rate Limiting

| Endpoint | Limit | Reasoning |
|---|---:|---|
| `POST /submit` | `10 per minute` per IP | Allows normal creator testing while blocking rapid spam. |
| `POST /submit` | `100 per day` per IP | Protects the free Groq tier from bulk abuse. |
| `POST /appeal` | `20 per day` per IP | Appeals should be uncommon and should not be spammed. |
| `GET /log` | `60 per minute` per IP | Allows grading/debugging without unlimited polling. |

The project uses Flask-Limiter with local memory storage:

```python
Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)
```

Rate-limit evidence from `scripts/smoke_m5.py`:

```text
[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429]
```

The first 10 requests succeeded. The 11th and 12th requests returned `429`, which confirms the `10 per minute` limit is active.

---

## Audit Log

The project uses structured JSONL logs in `data/audit_log.jsonl`. This file is append-only for audit events. `data/` is ignored by Git, but sample output is included here for grading visibility.

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
- whether an appeal has been filed

Each appeal logs:

- appeal ID
- content ID
- creator reasoning
- original attribution result
- original confidence score
- original signal scores
- status update to `under_review`

Sample audit entries:

```json
[
  {
    "event_type": "classification_decision",
    "content_id": "ab1fdd5c-a8f6-4ec8-9071-3c8db6ab6206",
    "creator_id": "m5-ai-user",
    "status": "classified",
    "appeal_filed": false,
    "attribution_result": "high_confidence_ai",
    "ai_likelihood": 0.95,
    "confidence_score": 0.95,
    "signal_scores": {
      "groq_llm": 0.95,
      "stylometric_heuristics": 0.95
    },
    "transparency_label": "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship."
  },
  {
    "event_type": "appeal_created",
    "appeal_id": "d5d2a335-c65e-452e-84b5-13469e1f107b",
    "content_id": "ab1fdd5c-a8f6-4ec8-9071-3c8db6ab6206",
    "creator_id": "m5-ai-user",
    "status": "under_review",
    "appeal_filed": true,
    "appeal_reasoning": "I wrote this myself from personal experience and want a human review.",
    "original_attribution_result": "high_confidence_ai",
    "original_confidence_score": 0.95
  },
  {
    "event_type": "status_updated",
    "content_id": "ab1fdd5c-a8f6-4ec8-9071-3c8db6ab6206",
    "old_status": "classified",
    "new_status": "under_review",
    "reason": "creator_appeal_received"
  }
]
```

---

## Known Limitations

### Short poetry with repetition

A short poem that intentionally repeats simple phrases could be misclassified as AI-like by the stylometric signal. Repetition ratio and vocabulary diversity are useful for detecting formulaic generated text, but they can also penalize valid poetic style. The short-text calibration reduces this risk by moving scores toward uncertainty when the input has fewer than 80 words.

### Formal human writing

Formal academic or policy-style writing can look AI-like because it often uses abstract vocabulary, smooth structure, and low emotional specificity. In testing, the formal human borderline sample scored higher than casual human writing, but still remained `uncertain` instead of becoming `high_confidence_ai`.

### Edited AI output

A human can edit AI output to add more irregularity and voice. The stylometric signal may then score it as more human-like, and the LLM may also be less certain. This system is not a forensic authorship tool; it provides transparency context only.

### No real authentication

The appeal endpoint accepts creator identifiers but does not implement production authentication. In a real platform, appeals should require authenticated creator ownership of the submitted content.

---

## Spec Reflection

One way the spec helped was forcing the confidence score and label thresholds to be defined before implementation. Because the thresholds were written in `planning.md`, the implementation could be checked directly against scores like `0.05`, `0.60`, and `0.95`. That prevented the label logic from becoming an accidental binary classifier at `0.5`.

One implementation divergence was the audit-log storage choice. The original planning considered SQLite, but the implementation used structured JSONL files. I kept JSONL because the project needed append-only event visibility for grading, not complex querying. JSONL also made `/log` easy to inspect and kept the stack simple for a small Flask project. If this were deployed for real, I would move the audit log to a database with authentication, indexing, and retention controls.

Another smaller divergence was supporting `creator_reasoning` on `/appeal` because the milestone instructions used that field name. The planning document originally described a `reason` field. The final endpoint accepts the milestone-compatible field so the documented curl command works.

---

## AI Usage

### Instance 1: Architecture and planning

I directed AI to help turn the project requirements into an architecture plan before writing implementation code. The AI produced the first version of the submission flow, appeal flow, component list, and detection-signal descriptions. I revised the plan to make the confidence-score semantics explicit: `0.0` means human-like, `0.5` means uncertain, and `1.0` means AI-like. I also made the AI threshold conservative because false positives are more harmful than false negatives for a creative platform.

### Instance 2: Flask implementation and signal integration

I directed AI to generate a Flask app skeleton with `/submit`, `/log`, Groq signal integration, and JSONL audit logging. I reviewed the generated code, installed missing dependencies, fixed local environment issues, and updated compatibility for Python 3.10 by replacing `datetime.UTC` with `timezone.utc`.

### Instance 3: Milestone 4 and 5 verification

I directed AI to generate the stylometric signal, confidence scoring, label mapping, appeal endpoint, and smoke tests. I verified the generated output with direct scripts and curl-style tests. I also reviewed the score behavior and kept short-text calibration because the initial AI-looking test was under 80 words and should not be over-labeled as high-confidence AI.

---

## Test Evidence

Run these commands from the repo root:

```bash
python -m compileall .
python scripts/test_labels_direct.py
python scripts/test_stylometric_direct.py
python scripts/smoke_m5.py
```

Observed final smoke-test result:

```text
PASS: Milestone 5 production layer is working.
```

Observed label test result:

```text
PASS: all three transparency label variants are reachable by threshold.
```

Observed rate-limit result:

```text
[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429]
```

---

## Portfolio Walkthrough Outline

A short walkthrough video should show:

1. The repo structure: `app.py`, `detection_signals.py`, `audit_log.py`, `planning.md`, and `README.md`.
2. `planning.md` architecture diagram and the two-signal design.
3. Running `python scripts/smoke_m5.py`.
4. The three label variants.
5. A `/submit` response showing both signals and the confidence score.
6. A `/appeal` response showing `under_review`.
7. `/log` output showing `classification_decision`, `appeal_created`, and `status_updated`.
8. A quick explanation of why uncertain labels and appeals matter for false-positive safety.