# Milestone 5 Notes

Milestone 5 adds the production layer on top of the Milestone 4 multi-signal pipeline.

## Implemented

- Final transparency-label mapping for all three planned variants.
- `POST /appeal` workflow.
- `GET /content/<content_id>` lookup.
- `GET /appeals` reviewer queue.
- `GET /log` structured audit-log output.
- Flask-Limiter setup with `storage_uri="memory://"`.
- Submit rate limit: `10 per minute;100 per day`.
- Appeal rate limit: `20 per day`.
- Log rate limit: `60 per minute`.
- Python 3.10-compatible UTC handling.

## Run

```bash
python -m pip install -r requirements.txt
python -m compileall .
python scripts/test_labels_direct.py
python scripts/test_stylometric_direct.py
python scripts/smoke_m5.py
```

Start the app:

```bash
python app.py
```

## Manual appeal test

Submit content first:

```bash
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text":"Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.","creator_id":"test-user-1"}' | python -m json.tool
```

Copy the returned `content_id`, then appeal:

```bash
curl -s -X POST http://127.0.0.1:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id":"PASTE-CONTENT-ID-HERE","creator_reasoning":"I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."}' | python -m json.tool
```

Check the audit log:

```bash
curl -s http://127.0.0.1:5000/log?limit=10 | python -m json.tool
```

## Rate-limit test

Run while the server is active:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text":"This is a test submission for rate limit testing purposes only.","creator_id":"ratelimit-test"}'
done
```

Expected shape:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```
