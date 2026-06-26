# Provenance Guard Planning

## Project Purpose

Provenance Guard is a backend system for creative sharing platforms. It accepts submitted text, analyzes whether the text appears more likely to be human-written, AI-generated, or uncertain, returns a confidence-aware transparency label, and records the decision in an audit log. If a creator disagrees with the classification, the system provides an appeal workflow that records the creator's reasoning and marks the content as under review.

The system is not designed to prove authorship perfectly. It is designed to provide transparent attribution context while avoiding overconfident claims, especially when a human creator could be harmed by a false AI label.

---

## Architecture

### Architecture Narrative

A creator submits a text item to `POST /submit`. The API validates the request, confirms the content is supported text, applies the rate limit, creates a content record, and sends the raw text into the detection pipeline. The pipeline runs two distinct signals: a Groq LLM classification signal and a deterministic stylometric heuristic signal. Each signal returns a normalized AI-likelihood score from `0.0` to `1.0`, where `0.0` means strongly human-like and `1.0` means strongly AI-like.

The confidence scorer combines both signal scores into one final `confidence_score`. In this project, `confidence_score` is an AI-likelihood confidence score, not a generic certainty score. A score near `0.0` means high-confidence human-like evidence, a score near `1.0` means high-confidence AI-like evidence, and scores near the middle mean uncertainty. The label generator maps the score into one of three transparency labels: `high_confidence_ai`, `high_confidence_human`, or `uncertain`. Every decision is written to the audit log before the API response is returned.

If a creator contests a classification, they submit `POST /appeal` with the content ID and their reason. The appeal handler verifies the content exists, records the appeal, changes the content status to `under_review`, and writes an audit-log entry linked to the original decision.

### Components

| Component | Responsibility |
|---|---|
| API Layer | Accepts requests, validates JSON, returns structured responses, and exposes endpoint contracts. |
| Rate Limiter | Protects `POST /submit` from accidental flooding and adversarial abuse. |
| Content Store | Stores content metadata, creator ID, title, classification result, confidence score, and review status. |
| Detection Pipeline | Runs attribution signals and normalizes their outputs. |
| Groq LLM Signal | Uses `llama-3.3-70b-versatile` to judge semantic and stylistic authorship patterns. |
| Stylometric Signal | Uses pure Python metrics to score sentence variation, vocabulary diversity, punctuation, and repetition. |
| Confidence Scorer | Combines signal scores into a final calibrated AI-likelihood confidence score. |
| Label Generator | Converts the final score into a reader-facing transparency label. |
| Appeal Handler | Captures creator appeals and marks the content as `under_review`. |
| Audit Logger | Records classification decisions, signal scores, labels, appeals, and status changes. |

### Submission Flow Diagram

```text
Client / Creative Platform
        |
        | POST /submit
        | {creator_id, title, content_type, content}
        v
API Layer
        |
        | validated text request
        v
Rate Limiter
        |
        | allowed request
        v
Content Store
        |
        | content_id + raw text metadata
        v
Detection Pipeline
        |
        | raw text
        +-------------------------------+
        |                               |
        v                               v
Groq LLM Signal                 Stylometric Signal
        |                               |
        | llm_ai_score                  | heuristic_ai_score
        | llm_verdict                   | metric breakdown
        | llm_rationale                 | heuristic rationale
        +---------------+---------------+
                        |
                        | normalized signal outputs
                        v
                Confidence Scorer
                        |
                        | combined confidence_score
                        | attribution_result
                        v
                Label Generator
                        |
                        | transparency_label text
                        v
                Audit Logger
                        |
                        | structured classification_decision event
                        v
                API Response
```

### Appeal Flow Diagram

```text
Creator / Client
        |
        | POST /appeal
        | {content_id, creator_id, reason, evidence_summary?}
        v
API Layer
        |
        | validated appeal request
        v
Appeal Handler
        |
        | lookup original content + decision
        v
Content Store
        |
        | update status: classified -> under_review
        v
Audit Logger
        |
        | appeal_created event
        | status_updated event
        v
API Response
        |
        | {appeal_id, content_id, status: under_review}
```

---

## Detection Signals

### Signal 1: Groq LLM Classification

**What it measures**

The Groq signal asks an LLM to evaluate whether the submitted text reads more like human-written text or AI-generated text. It captures holistic patterns that are difficult to measure with simple counters, including generic phrasing, overly smooth structure, lack of distinctive voice, unnatural balance, semantic coherence, and signs of personal irregularity.

**Why this can differ between human and AI writing**

AI-generated text often has polished transitions, even pacing, low-risk wording, and generic coherence. Human creative writing often contains uneven rhythm, unusual phrasing, inconsistent structure, or voice-specific decisions. The LLM can judge these broad patterns better than a purely statistical heuristic.

**Output shape**

```json
{
  "signal": "groq_llm",
  "ai_score": 0.0,
  "verdict": "human | ai | uncertain",
  "rationale": "Short explanation of the model's reasoning.",
  "limitations": ["Specific uncertainty or blind spot."]
}
```

**Score meaning**

| `ai_score` Range | Meaning |
|---:|---|
| `0.00 - 0.20` | Strongly human-like according to the LLM. |
| `0.21 - 0.59` | Weak or mixed evidence, leaning human or uncertain. |
| `0.60 - 0.84` | Some AI-like evidence but not enough alone for a high-confidence AI label. |
| `0.85 - 1.00` | Strong AI-like evidence according to the LLM. |

**Blind spots**

- A polished human writer can look AI-like.
- Human-edited AI text can look human-like.
- Very short content may not contain enough evidence.
- Poems, experimental prose, and non-native English writing may be misread as AI-like.
- The LLM is not proof of authorship and must never be treated as final evidence by itself.

### Signal 2: Stylometric Heuristics

**What it measures**

The stylometric signal computes structural writing metrics in pure Python. It does not call an external model. It measures statistical properties of the text:

| Metric | What It Captures | AI-like Pattern Used by This Project |
|---|---|---|
| `sentence_length_variance` | Whether sentence lengths vary naturally. | Low variance can indicate machine-like uniformity. |
| `type_token_ratio` | Vocabulary diversity. | Very low diversity can indicate generic or repetitive writing. |
| `punctuation_density` | Punctuation use per word. | Extremely uniform or sparse punctuation can be suspicious. |
| `repetition_ratio` | Repeated words or repeated 3-word phrases. | Repeated boilerplate phrasing can indicate AI generation. |
| `transition_phrase_density` | Use of formulaic transitions. | Heavy use of generic transitions can indicate AI-like style. |
| `average_word_length` | Rough lexical complexity. | Overly consistent word complexity can support other AI-like signals. |

**Why this can differ between human and AI writing**

AI writing often has smoother sentence pacing and more consistent structure. Human creative writing often has more uneven rhythm, fragments, intentional repetition, abrupt punctuation, and unusual vocabulary choices. These metrics give a deterministic structural signal that is independent from the LLM's semantic judgment.

**Output shape**

```json
{
  "signal": "stylometric_heuristics",
  "ai_score": 0.0,
  "metrics": {
    "word_count": 0,
    "sentence_count": 0,
    "sentence_length_variance": 0.0,
    "type_token_ratio": 0.0,
    "punctuation_density": 0.0,
    "repetition_ratio": 0.0,
    "transition_phrase_density": 0.0,
    "average_word_length": 0.0
  },
  "rationale": "Short explanation of which metrics pushed the score up or down."
}
```

**Planned heuristic scoring formula**

```text
stylometric_ai_score = clamp(
    0.30 * sentence_uniformity_score
  + 0.25 * vocabulary_repetition_score
  + 0.20 * phrase_repetition_score
  + 0.15 * punctuation_pattern_score
  + 0.10 * transition_phrase_score,
  0.0,
  1.0
)
```

**Blind spots**

- Short text produces unstable statistics.
- Poetry can intentionally use repetition and simple vocabulary.
- Formulaic human writing can look AI-like.
- Carefully edited AI text may look structurally human.
- The heuristic cannot understand meaning, sincerity, parody, cultural context, or author intent.

---

## Confidence Scoring and Uncertainty Representation

### Score Definition

The API returns `confidence_score` as a calibrated AI-likelihood confidence score:

```text
0.0 = strongest human-like evidence
0.5 = maximum uncertainty / mixed evidence
1.0 = strongest AI-like evidence
```

A `confidence_score` of `0.60` means the system sees mild-to-moderate AI-like evidence, but the evidence is not strong enough to label the content as AI-generated. It should return the uncertain label. This prevents the system from turning a weak lean into a public accusation.

### Signal Combination

The first implementation will combine the two signals with a weighted average:

```text
raw_combined_score = (0.55 * groq_llm.ai_score) + (0.45 * stylometric_heuristics.ai_score)
```

The LLM receives slightly more weight because it can evaluate semantics and style at a higher level. The stylometric signal still receives substantial weight because it is deterministic, explainable, and independent from the LLM.

### Calibration Rules

After the weighted average, the system applies two uncertainty adjustments:

```text
if abs(groq_llm.ai_score - stylometric_heuristics.ai_score) >= 0.35:
    final_score = 0.5 + ((raw_combined_score - 0.5) * 0.80)
else:
    final_score = raw_combined_score

if word_count < 80:
    final_score = 0.5 + ((final_score - 0.5) * 0.70)
```

Reasoning:

- If the two signals disagree strongly, the final score moves closer to `0.5` because the system should admit uncertainty.
- If the text is very short, the final score moves closer to `0.5` because there is less evidence.

### Label Thresholds

| Final `confidence_score` | Internal Result | Public Label Variant |
|---:|---|---|
| `0.00 - 0.20` | `high_confidence_human` | High-confidence human label |
| `0.21 - 0.84` | `uncertain` | Uncertain label |
| `0.85 - 1.00` | `high_confidence_ai` | High-confidence AI label |

### Why the Thresholds Are Asymmetric

False positives are especially harmful in this domain because incorrectly labeling a human creator's work as AI-generated can damage trust and reputation. For that reason, the AI threshold is intentionally high at `0.85`. Borderline or mixed cases should remain uncertain instead of being forced into an AI label.

### Required Examples

| Example Score | System Interpretation | Label Returned |
|---:|---|---|
| `0.05` | Strong human-like evidence. | `high_confidence_human` |
| `0.51` | Very close to uncertain center. | `uncertain` |
| `0.60` | Some AI-like evidence, not enough for AI label. | `uncertain` |
| `0.72` | Meaningful AI-like evidence, still below high-confidence threshold. | `uncertain` |
| `0.95` | Strong AI-like evidence. | `high_confidence_ai` |

---

## Transparency Label Design

The label text must be copied exactly into `README.md` later. The backend will return the selected text in the `transparency_label` field.

| Variant | Exact Label Text |
|---|---|
| `high_confidence_ai` | "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship." |
| `high_confidence_human` | "Provenance Guard found strong signs that this text was likely written by a human. This label is based on multiple detection signals and does not prove authorship." |
| `uncertain` | "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made." |

### Label Design Rationale

- The AI label says `may have been AI-generated`, not `was AI-generated`, because the system is probabilistic.
- The human label says `likely written by a human`, not `verified human`, because the base system does not verify identity or writing process.
- The uncertain label explicitly avoids a strong claim.
- All labels mention that multiple signals were used so the user knows the result is not based on one detector.

---

## Appeals Workflow

### Who Can Submit an Appeal

For the course project, any request with a `creator_id` matching the original content's `creator_id` may submit an appeal. There is no full authentication system in the first version, but the API will still check that the appeal creator matches the stored creator ID for the content.

### Appeal Request Data

`POST /appeal` accepts:

```json
{
  "content_id": "content_abc123",
  "creator_id": "creator_123",
  "reason": "I wrote this myself and can provide drafts showing my writing process.",
  "evidence_summary": "Optional short note, such as draft history, outline, or process evidence."
}
```

Validation rules:

| Field | Required | Rule |
|---|---|---|
| `content_id` | Yes | Must reference an existing content record. |
| `creator_id` | Yes | Must match the original content creator. |
| `reason` | Yes | Must be non-empty and at least 10 characters. |
| `evidence_summary` | No | Optional string, maximum 1000 characters. |

### System Behavior When Appeal Is Received

1. Validate the JSON body.
2. Look up the original content record.
3. Reject the appeal if the `creator_id` does not match the content owner.
4. Create an appeal record with status `open`.
5. Update the content status from `classified` to `under_review`.
6. Preserve the original classification result and confidence score.
7. Write an `appeal_created` audit event.
8. Write a `status_updated` audit event.
9. Return `appeal_id`, `content_id`, and `status: under_review`.

### Reviewer Queue View

A human reviewer opening the appeal queue should see:

| Field | Purpose |
|---|---|
| `appeal_id` | Unique appeal reference. |
| `content_id` | Links appeal to original submission. |
| `creator_id` | Identifies the contesting creator. |
| `title` | Helps reviewer identify the work. |
| `content_excerpt` | First 300 characters of submitted text. |
| `original_result` | Prior result: `high_confidence_ai`, `high_confidence_human`, or `uncertain`. |
| `original_confidence_score` | Original calibrated score. |
| `signal_scores` | LLM score and stylometric score. |
| `transparency_label` | Label that was shown. |
| `appeal_reason` | Creator's explanation. |
| `evidence_summary` | Optional process evidence summary. |
| `status` | `open`, `under_review`, `resolved`, or `rejected`. |
| `created_at` | Appeal timestamp. |

Automated re-classification is not required in the first version. The appeal system exists to preserve creator recourse and make contested decisions visible.

---

## API Surface

### `POST /submit`

Accepts text content for attribution analysis.

**Request**

```json
{
  "creator_id": "creator_123",
  "title": "Short Story Draft",
  "content_type": "text",
  "content": "The submitted poem, story excerpt, or blog post goes here."
}
```

**Success Response: `200 OK`**

```json
{
  "content_id": "content_abc123",
  "status": "classified",
  "attribution_result": "uncertain",
  "confidence_score": 0.60,
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
      },
      "rationale": "The structural metrics are mixed and do not support a strong attribution claim."
    }
  ]
}
```

**Validation Errors**

| Condition | Response |
|---|---|
| Missing `creator_id` | `400 Bad Request` |
| Missing or empty `content` | `400 Bad Request` |
| Unsupported `content_type` | `400 Bad Request` |
| Request exceeds rate limit | `429 Too Many Requests` |
| Groq API unavailable | Return response using heuristic only, mark LLM signal unavailable, and log degraded mode. |

### `POST /appeal`

Allows a creator to contest a classification.

**Request**

```json
{
  "content_id": "content_abc123",
  "creator_id": "creator_123",
  "reason": "I wrote this myself and can provide drafts showing my writing process.",
  "evidence_summary": "I have an outline and earlier drafts saved before posting."
}
```

**Success Response: `200 OK`**

```json
{
  "appeal_id": "appeal_001",
  "content_id": "content_abc123",
  "status": "under_review",
  "message": "Appeal received. The original classification has been marked for review."
}
```

### `GET /content/<content_id>`

Returns the stored classification result for one submitted item.

### `GET /appeals`

Returns open appeals for the reviewer queue.

### `GET /log`

Returns structured audit-log entries for grading and debugging. The README may also show sample log output with at least three entries.

### `GET /health`

Returns a simple local health check.

---

## Rate Limiting Plan

| Endpoint | Limit | Reasoning |
|---|---:|---|
| `POST /submit` | `10 per minute` per IP | Allows normal testing and creator usage while blocking rapid spam. |
| `POST /submit` | `100 per day` per IP | Protects the free Groq tier and prevents bulk abuse. |
| `POST /appeal` | `20 per day` per IP | Appeals should be rare; this prevents appeal spam. |
| `GET /log` | `60 per minute` per IP | Enough for grading/debugging without unlimited polling. |
| `GET /health` | No strict limit | Local operational check only. |

These values are intentionally conservative for a student project that may use a free external LLM tier. The README must document these exact limits and explain the reasoning.

---

## Audit Log Plan

The first implementation will use structured JSONL files because Milestone 3 only needs append-only decision logging and simple grading visibility through GET /log. A later version may upgrade this to SQLite if the appeal workflow needs richer querying.

### Main Tables

| Table | Purpose |
|---|---|
| `content` | Stores submitted content metadata, final status, result, score, and label text. |
| `classification_decisions` | Stores one classification decision per submission, including signal outputs. |
| `appeals` | Stores creator appeals linked to content records. |
| `audit_log` | Stores append-only structured events for decisions, appeals, and status changes. |

### Audit Event Types

| Event Type | Required Data |
|---|---|
| `classification_decision` | `content_id`, timestamp, result, confidence score, signal names, signal scores, label text. |
| `appeal_created` | `appeal_id`, `content_id`, `creator_id`, timestamp, appeal reason, evidence summary if provided. |
| `status_updated` | `content_id`, old status, new status, timestamp, reason. |
| `signal_unavailable` | `content_id`, signal name, error category, fallback behavior. |

### Sample Log Entries for README Later

```json
[
  {
    "event_type": "classification_decision",
    "content_id": "content_001",
    "attribution_result": "high_confidence_ai",
    "confidence_score": 0.91,
    "signals_used": ["groq_llm", "stylometric_heuristics"],
    "signal_scores": {"groq_llm": 0.94, "stylometric_heuristics": 0.88},
    "label_text": "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship."
  },
  {
    "event_type": "appeal_created",
    "appeal_id": "appeal_001",
    "content_id": "content_001",
    "creator_id": "creator_123",
    "reason": "I wrote this myself and can provide drafts showing my writing process."
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

---

## Anticipated Edge Cases

| Edge Case | Why It Is Hard | Planned Handling |
|---|---|---|
| Short poem with repetition and simple vocabulary | Stylometric heuristics may treat repetition and low vocabulary diversity as AI-like even when it is an intentional poetic device. | Move short text scores toward `0.5`; use uncertain label unless both signals strongly agree. |
| Polished human essay or blog post | Clean structure and balanced transitions may look AI-generated. | Require `0.85+` before AI label; preserve appeal path. |
| Non-native English writing | Unusual grammar or phrasing may confuse both the LLM and heuristics. | Avoid claiming proof; keep borderline scores uncertain. |
| Human-edited AI draft | Text may contain both AI-like and human-like features. | Treat as mixed evidence; return uncertain unless strong agreement exists. |
| AI text intentionally made messy | The stylometric signal may be fooled by inserted fragments, typos, or irregular punctuation. | Rely on multi-signal design; log both scores for reviewer inspection. |
| Very short submission under 80 words | Not enough sentence or vocabulary data for stable metrics. | Apply short-text calibration toward `0.5`; mark uncertainty in signal rationale. |
| Quoted or mixed-author content | The submitted text may include quotes, excerpts, or collaborative writing. | Classification applies only to submitted text as a whole; no claim about individual sections. |

---

## AI Tool Plan

### M3: Submission Endpoint + First Signal

**Spec sections to provide to the AI tool**

- `## Architecture`
- `## Detection Signals` — Signal 1 only
- `## API Surface` — `POST /submit` and `GET /health`
- `## Audit Log Plan` — classification event shape only

**Ask the AI tool to generate**

- Flask app skeleton.
- `POST /submit` endpoint with request validation.
- `GET /health` endpoint.
- Groq LLM signal function using `llama-3.3-70b-versatile`.
- Basic content ID generation.
- Basic structured response shape.
- `.env` loading for `GROQ_API_KEY`.

**Verification plan**

- Call the Groq signal function directly with one clearly AI-style sample and one clearly human-style sample.
- Confirm the function returns valid JSON with `signal`, `ai_score`, `verdict`, `rationale`, and `limitations`.
- Test `POST /submit` with missing content and confirm `400`.
- Test `POST /submit` with valid content and confirm response includes `content_id`, `confidence_score`, `transparency_label`, and `signals`.

### M4: Second Signal + Confidence Scoring

**Spec sections to provide to the AI tool**

- `## Detection Signals`
- `## Confidence Scoring and Uncertainty Representation`
- `## Architecture`
- `## Anticipated Edge Cases`

**Ask the AI tool to generate**

- Pure Python stylometric heuristic function.
- Metric extraction helpers for word count, sentence count, sentence length variance, type-token ratio, punctuation density, repetition ratio, transition phrase density, and average word length.
- Score normalization helpers using `clamp()`.
- Signal combiner using the `0.55 / 0.45` weighted average.
- Disagreement calibration rule.
- Short-text calibration rule.

**Verification plan**

- Test the stylometric signal directly on at least three samples: repetitive poem, generic AI-style paragraph, and irregular human-style paragraph.
- Confirm all scores stay within `0.0` to `1.0`.
- Confirm `confidence_score = 0.60` maps to `uncertain`, not AI.
- Confirm `0.95` maps to `high_confidence_ai` and `0.05` maps to `high_confidence_human`.
- Confirm signal disagreement moves the final score closer to `0.5`.

### M5: Production Layer

**Spec sections to provide to the AI tool**

- `## Transparency Label Design`
- `## Appeals Workflow`
- `## API Surface`
- `## Rate Limiting Plan`
- `## Audit Log Plan`
- `## Architecture`

**Ask the AI tool to generate**

- Label generation function with the three exact label strings.
- SQLite schema and initialization.
- Audit logger for classification, appeal, and status update events.
- `POST /appeal` endpoint.
- `GET /content/<content_id>` endpoint.
- `GET /appeals` reviewer queue endpoint.
- `GET /log` endpoint.
- Flask-Limiter configuration using the planned limits.

**Verification plan**

- Confirm all three label variants are reachable by directly testing scores `0.05`, `0.60`, and `0.95`.
- Submit a classification, then submit an appeal using the same `creator_id` and confirm content status becomes `under_review`.
- Attempt an appeal with a different `creator_id` and confirm the API rejects it.
- Call `GET /log` and confirm at least three visible event entries exist after classification and appeal testing.
- Confirm `POST /submit` returns `429` when rate limits are exceeded.
