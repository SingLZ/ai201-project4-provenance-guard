# Provenance Guard - Milestone 3

This Milestone 3 implementation adds:

- Flask app skeleton
- `POST /submit`
- Signal 1: Groq LLM classification
- placeholder confidence and label
- structured JSONL audit log
- `GET /log`
- direct signal smoke script

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# or: .venv\Scripts\activate    # Windows Command Prompt / PowerShell
pip install -r requirements.txt
cp .env.example .env
```

Put your Groq key in `.env`:

```bash
GROQ_API_KEY=your_key_here
```

Without a key, the app uses an explicit local mock fallback marked with `"mocked": true` so the route and audit log can still be tested.

## Run direct Signal 1 check

```bash
python scripts/test_signal_direct.py
```

## Run Flask app

```bash
python app.py
```

## Test `/submit`

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool
```

Expected fields:

```json
{
  "content_id": "uuid-here",
  "creator_id": "test-user-1",
  "attribution": "likely_ai | likely_human | uncertain",
  "confidence": 0.5,
  "label": "Placeholder label: final transparency labels will be implemented in Milestone 5.",
  "signals": {
    "groq_llm": {
      "signal": "groq_llm",
      "ai_score": 0.5,
      "verdict": "human | ai | uncertain",
      "rationale": "...",
      "limitations": ["..."],
      "mocked": false
    }
  },
  "status": "classified"
}
```

Save the `content_id` for Milestone 5 appeals.

## Inspect audit log

```bash
curl -s http://localhost:5000/log?limit=3 | python -m json.tool
```

Audit entries are written to:

```text
data/audit_log.jsonl
```

Each classification entry includes:

- `timestamp`
- `event_type`
- `content_id`
- `creator_id`
- `attribution`
- `confidence`
- `llm_score`
- `llm_verdict`
- `llm_mocked`
- `status`

## No-code boundary for this milestone

Not implemented yet:

- Signal 2 stylometric heuristics
- final weighted confidence scoring
- final transparency label variants
- appeals workflow
- rate-limit documentation in README final form
