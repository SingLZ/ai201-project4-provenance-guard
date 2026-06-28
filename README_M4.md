# Provenance Guard — Milestone 4 Notes

Milestone 4 adds the second detection signal and real confidence scoring.

## Implemented

- `POST /submit` now runs two signals:
  - `groq_llm`
  - `stylometric_heuristics`
- Combined scoring follows `planning.md`:
  - `0.55 * groq_llm.ai_score`
  - `0.45 * stylometric_heuristics.ai_score`
- Calibration rules:
  - Signal disagreement moves the score toward `0.5`.
  - Short text under 80 words moves the score toward `0.5`.
- Response fields now match the final API contract:
  - `attribution_result`
  - `ai_likelihood`
  - `confidence_score`
  - `transparency_label`
  - `signals`
- Audit log now records both signal scores and the combined result.

## Run checks

```bash
python -m compileall .
python scripts/test_stylometric_direct.py
python scripts/smoke_m4.py
```

## Start server

```bash
python app.py
```

## Test submit

```bash
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.", "creator_id": "test-user-1"}' | python -m json.tool
```

## Test log

```bash
curl -s http://127.0.0.1:5000/log?limit=4 | python -m json.tool
```

## Expected shape

```json
{
  "content_id": "...",
  "creator_id": "test-user-1",
  "status": "classified",
  "attribution_result": "uncertain",
  "ai_likelihood": 0.6,
  "confidence_score": 0.6,
  "transparency_label": "...",
  "signals": [
    {"signal": "groq_llm", "ai_score": 0.6},
    {"signal": "stylometric_heuristics", "ai_score": 0.7, "metrics": {}}
  ]
}
```

Because the AI threshold is intentionally high (`0.85`), many moderately AI-like samples should still return `uncertain`.
