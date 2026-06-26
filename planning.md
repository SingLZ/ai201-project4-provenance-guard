# Provenance Guard Planning

## Milestone 1: Understand the System and Define the Architecture

### Project Purpose

Provenance Guard is a backend system for creative sharing platforms. It accepts submitted text, analyzes whether the text appears more likely to be human-written, AI-generated, or uncertain, returns a confidence-aware transparency label, and records the decision in an audit log. If a creator disagrees with the classification, the system provides an appeal workflow that records the creator's reasoning and marks the content as under review.

The system is not designed to prove authorship perfectly. It is designed to provide transparent attribution context while avoiding overconfident claims, especially when a human creator could be harmed by a false AI label.

---

## Architecture

### Architecture Narrative

A creator submits a piece of text to `POST /submit`. The API layer validates the request, checks that the content is non-empty text, applies the submission rate limit, and creates a new content record.

The text then enters the detection pipeline. The pipeline runs two independent detection signals:

1. **Groq LLM classification signal**: asks an LLM to judge whether the text reads more like human writing or AI-generated writing.
2. **Stylometric heuristic signal**: computes measurable writing statistics such as sentence length variance, vocabulary diversity, punctuation density, and repetition.

Each signal returns a normalized AI-likelihood score between `0.0` and `1.0`, where `0.0` means strongly human-like and `1.0` means strongly AI-like. The confidence scorer combines the two signal scores using weighted averaging. The first implementation will weight the signals equally because they measure different properties of the same text: semantic/style judgment and structural writing patterns.

The combined score is passed to the label generator. The label generator converts the score into one of three user-facing outcomes:

- `high_confidence_ai`
- `high_confidence_human`
- `uncertain`

The label generator intentionally uses a higher threshold before calling something AI-generated because false positives are more damaging to human creators than false negatives. If the result is not strong enough, the system returns an uncertain label rather than forcing a binary decision.

After the label is generated, the audit logger records the full decision: content ID, timestamp, final attribution result, confidence score, each signal score, signal explanations, and the label text returned to users. The API then returns the structured response to the platform.

If a creator contests the result, they submit an appeal to `POST /appeal`. The API validates the appeal, finds the original content decision, stores the creator's reasoning, updates the content status to `under_review`, and writes a second audit-log entry linking the appeal to the original decision. Automated re-classification is not required for the first version.

---

### Components

| Component | Responsibility |
|---|---|
| API Layer | Accepts requests, validates input, returns JSON responses, enforces endpoint contracts. |
| Rate Limiter | Limits submission traffic to reduce abuse and accidental flooding. |
| Content Store | Stores submitted content metadata, final classification, confidence score, and review status. |
| Detection Pipeline | Runs all attribution signals and returns normalized signal results. |
| Groq LLM Signal | Uses an LLM to classify text based on semantic and stylistic patterns. |
| Stylometric Signal | Uses pure Python heuristics to score writing structure and statistical variation. |
| Confidence Scorer | Combines signal outputs into one final AI-likelihood score. |
| Label Generator | Converts score into a plain-language transparency label. |
| Appeal Handler | Captures creator appeals and moves content into `under_review` status. |
| Audit Logger | Records every decision and appeal in structured form for traceability. |

---

### Submission Flow Diagram

```text
Client / Creative Platform
        |
        | POST /submit
        | raw text, creator_id, title
        v
API Layer
        |
        | validated text
        v
Rate Limiter
        |
        | allowed request
        v
Content Store
        |
        | content_id + raw text
        v
Detection Pipeline
        |
        | raw text
        +----------------------------+
        |                            |
        v                            v
Groq LLM Signal              Stylometric Signal
        |                            |
        | llm_ai_score               | heuristic_ai_score
        | llm_explanation            | heuristic_metrics
        +-------------+--------------+
                      |
                      | signal scores
                      v
              Confidence Scorer
                      |
                      | combined_ai_score
                      | confidence_score
                      v
              Label Generator
                      |
                      | attribution_result
                      | transparency_label
                      v
              Audit Logger
                      |
                      | structured decision log
                      v
              API Response
```

---

### Appeal Flow Diagram

```text
Creator / Client
        |
        | POST /appeal
        | content_id, creator_id, reason
        v
API Layer
        |
        | validated appeal request
        v
Appeal Handler
        |
        | original decision lookup
        v
Content Store
        |
        | update content status = under_review
        v
Audit Logger
        |
        | appeal log entry linked to original content_id
        v
API Response
        |
        | appeal_id, content_id, status = under_review
```

---

## Detection Signal Decisions

### Signal 1: Groq LLM Classification

**What it measures**

This signal asks the LLM to evaluate whether the submitted text reads more like human-written text or AI-generated text. It captures broad semantic and stylistic qualities such as:

- generic or over-polished phrasing
- unnatural coherence
- repetitive explanation patterns
- lack of specific voice
- overly balanced structure
- signs of human irregularity or idiosyncratic expression

**Why this may differ between human and AI writing**

AI-generated writing often has smoother structure, more generic transitions, and fewer personal irregularities. Human creative writing may include uneven rhythm, surprising phrasing, inconsistent structure, or unusual word choices. The LLM can evaluate these higher-level patterns better than simple counting rules.

**Blind spots**

- A polished human writer can look AI-like.
- An edited AI text can look human-like.
- Short submissions may not give enough evidence.
- Poems, experimental writing, and non-native writing may confuse the model.
- The LLM is not proof of authorship; it is only one signal.

---

### Signal 2: Stylometric Heuristics

**What it measures**

This signal computes structural writing metrics in pure Python, including:

- average sentence length
- sentence length variance
- type-token ratio, meaning vocabulary diversity
- punctuation density
- repeated phrase or repeated word ratio
- average word length

These metrics are converted into a normalized AI-likelihood score.

**Why this may differ between human and AI writing**

AI text often has more uniform sentence lengths, predictable punctuation, and smoother paragraph structure. Human writing, especially creative writing, often has more variation: short fragments, long sentences, unusual punctuation, repetition for effect, and inconsistent rhythm.

**Blind spots**

- Very short text gives unstable metrics.
- Poetry can intentionally break normal sentence rules.
- Formulaic human writing may look AI-like.
- Human-edited AI text may pass as human.
- The heuristic cannot understand meaning, intent, humor, or emotional authenticity.

---

## Confidence Scoring Plan

The system will produce a combined AI-likelihood score from `0.0` to `1.0`.

| Score Range | Internal Meaning | User-Facing Result |
|---:|---|---|
| `0.00 - 0.15` | Strongly human-like | `high_confidence_human` |
| `0.16 - 0.84` | Not strong enough either way | `uncertain` |
| `0.85 - 1.00` | Strongly AI-like | `high_confidence_ai` |

This threshold design intentionally makes the AI label harder to trigger than the uncertain label. A false positive can damage a real creator's reputation, so borderline cases should stay uncertain.

The API will include:

- `ai_likelihood`: raw combined score where higher means more AI-like.
- `confidence_score`: confidence in the displayed result.
- `attribution_result`: final classification category.
- `transparency_label`: exact text shown to readers.

For example:

- `ai_likelihood = 0.51` should produce an `uncertain` label.
- `ai_likelihood = 0.95` should produce a `high_confidence_ai` label.
- `ai_likelihood = 0.05` should produce a `high_confidence_human` label.

---

## Draft Transparency Labels

These are the planned label variants. The exact final text should also be copied into `README.md`.

| Variant | Exact Label Text |
|---|---|
| High-confidence AI | "Provenance Guard found strong signs that this text may have been AI-generated. This label is based on multiple detection signals and is not a final judgment of authorship." |
| High-confidence human | "Provenance Guard found strong signs that this text was likely written by a human. This label is based on multiple detection signals and does not prove authorship." |
| Uncertain | "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made." |

---

## False Positive Scenario

A human creator submits a short story excerpt written in a very clean and polished style. The LLM signal rates it as somewhat AI-like because the structure is smooth. The stylometric signal also rates it as somewhat AI-like because sentence lengths are consistent. The combined AI-likelihood score is `0.72`.

The system does not label this as high-confidence AI because the score is below the `0.85` AI threshold. Instead, it returns the uncertain label. This protects the creator from being publicly marked as AI-generated when the evidence is not strong enough.

If the score were higher and the creator believed the result was wrong, the creator could submit an appeal through `POST /appeal`. The appeal would capture the creator's explanation, preserve the original decision, update the content status to `under_review`, and add an appeal entry to the audit log. The public-facing platform could then hide the strong label or display the review status while a moderator reviews the case.

This flow reflects the main design principle: uncertainty should be visible, and creators must have a path to contest the system.

---

## API Surface Draft

### `POST /submit`

Accepts text content for attribution analysis.

**Request body**

```json
{
  "creator_id": "creator_123",
  "title": "Short Story Draft",
  "content_type": "text",
  "content": "The submitted poem, story excerpt, or blog post goes here."
}
```

**Response body**

```json
{
  "content_id": "content_abc123",
  "status": "classified",
  "attribution_result": "uncertain",
  "ai_likelihood": 0.51,
  "confidence_score": 0.51,
  "transparency_label": "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made.",
  "signals": [
    {
      "name": "groq_llm",
      "score": 0.55,
      "explanation": "The text has some polished structure, but the evidence is not strong."
    },
    {
      "name": "stylometric_heuristics",
      "score": 0.47,
      "explanation": "Sentence variation and vocabulary diversity do not strongly indicate AI generation."
    }
  ]
}
```

---

### `POST /appeal`

Allows a creator to contest a classification.

**Request body**

```json
{
  "content_id": "content_abc123",
  "creator_id": "creator_123",
  "reason": "I wrote this myself and can provide drafts showing my writing process."
}
```

**Response body**

```json
{
  "appeal_id": "appeal_001",
  "content_id": "content_abc123",
  "status": "under_review",
  "message": "Appeal received. The original classification has been marked for review."
}
```

---

### `GET /content/<content_id>`

Returns the stored classification result for a submitted item.

**Response body**

```json
{
  "content_id": "content_abc123",
  "creator_id": "creator_123",
  "title": "Short Story Draft",
  "status": "under_review",
  "attribution_result": "uncertain",
  "ai_likelihood": 0.51,
  "confidence_score": 0.51,
  "transparency_label": "Provenance Guard could not confidently determine whether this text was human-written or AI-generated. The result is uncertain, so no strong attribution claim is being made."
}
```

---

### `GET /log`

Returns structured audit log entries for grading and debugging.

**Response body**

```json
{
  "entries": [
    {
      "event_type": "classification_decision",
      "content_id": "content_abc123",
      "attribution_result": "uncertain",
      "ai_likelihood": 0.51,
      "confidence_score": 0.51,
      "signals_used": ["groq_llm", "stylometric_heuristics"]
    },
    {
      "event_type": "appeal_created",
      "content_id": "content_abc123",
      "appeal_id": "appeal_001",
      "status": "under_review",
      "reason": "I wrote this myself and can provide drafts showing my writing process."
    }
  ]
}
```

---

### `GET /health`

Simple health check for local testing.

**Response body**

```json
{
  "status": "ok"
}
```

---

## Initial Rate Limit Decision

The submission endpoint should be rate-limited because it calls an external LLM and could be abused. Initial planned limits:

| Endpoint | Limit | Reason |
|---|---:|---|
| `POST /submit` | 10 requests per minute per IP | Enough for normal testing and creator usage, but blocks rapid spam. |
| `POST /submit` | 100 requests per day per IP | Prevents large-scale abuse of the free Groq tier. |
| `POST /appeal` | 20 requests per day per IP | Appeals should be rare and should not be spammed. |
| `GET /log` | No strict production limit for local project; optional 60/min | Mainly used for grading and debugging. |

These values can be adjusted after testing, but the first version prioritizes protecting the submission endpoint.

---

## Data and Audit Log Plan

The first implementation can use SQLite because it is built into Python and does not require an external service.

### Main records

| Record | Purpose |
|---|---|
| `content` | Stores submitted content metadata and final status. |
| `classification_decisions` | Stores scores, result, label text, and signal details. |
| `appeals` | Stores appeal reason and links back to the original content. |
| `audit_log` | Stores append-only structured events for decisions and appeals. |

### Audit events to capture

| Event Type | Required Data |
|---|---|
| `classification_decision` | content ID, timestamp, attribution result, confidence score, AI likelihood, signal scores, signal names, label text |
| `appeal_created` | appeal ID, content ID, creator ID, timestamp, creator reason |
| `status_updated` | content ID, old status, new status, timestamp, reason |

---

## Milestone 1 Checkpoint

- The text submission path is defined from API request to transparency label.
- The appeal path is defined from creator appeal to audit log entry.
- Two distinct detection signals are chosen: Groq LLM classification and stylometric heuristics.
- The false-positive risk is handled through conservative thresholds, uncertain labels, and appeals.
- The first API contract is defined before implementation.
- The architecture diagram includes both submission and appeal flows.
