# Codex Prompt — Milestone 4

Recommended reasoning level: **medium**.

Use the existing Flask project in this repo. Implement Milestone 4 only. Do not add appeals yet.

Spec sections to follow:
- `planning.md` → `## Detection Signals`
- `planning.md` → `## Confidence Scoring and Uncertainty Representation`
- `planning.md` → `## Architecture`
- `planning.md` → `## Anticipated Edge Cases`

Tasks:
1. Add Signal 2 as a pure Python stylometric heuristic function.
2. Compute at least these metrics:
   - word count
   - sentence count
   - sentence length variance
   - type-token ratio
   - punctuation density
   - repetition ratio
   - transition phrase density
   - average word length
3. Return Signal 2 in this shape:
   ```json
   {
     "signal": "stylometric_heuristics",
     "ai_score": 0.0,
     "metrics": {},
     "rationale": "..."
   }
   ```
4. Combine Signal 1 and Signal 2 exactly as planning.md says:
   ```text
   raw_combined_score = (0.55 * groq_llm.ai_score) + (0.45 * stylometric_heuristics.ai_score)
   ```
5. Apply the planning.md calibration rules:
   - If the two scores differ by at least 0.35, move the combined score 20% closer to 0.5.
   - If word count is under 80, move the final score 30% closer to 0.5.
6. Use these thresholds exactly:
   - `0.00 - 0.20` → `high_confidence_human`
   - `0.21 - 0.84` → `uncertain`
   - `0.85 - 1.00` → `high_confidence_ai`
7. Update `POST /submit` so it returns final field names:
   - `content_id`
   - `status`
   - `attribution_result`
   - `ai_likelihood`
   - `confidence_score`
   - `transparency_label`
   - `signals`
8. Update the audit log to include:
   - `llm_score`
   - `stylometric_score`
   - `signal_scores`
   - `raw_combined_score`
   - `confidence_score`
   - `attribution_result`

Validation:
- Run `python -m compileall .`
- Run `python scripts/test_stylometric_direct.py`
- Run `python scripts/smoke_m4.py`
- Do not run broad or expensive tests.
- Do not implement Milestone 5.
