# CareChat

A chat assistant that helps patients understand their medical reports and get trustworthy health
information in plain language. It educates and never diagnoses.

**Status:** MVP code. Not for real patients yet: run the safety evaluations, load reference content,
and complete the compliance steps below first.

## What it does

- **Explains lab reports.** Upload a PDF; Claude reads it into a results table (test, value, unit,
  range and flag exactly as printed), then explains it in chat.
- **Answers health questions** from MedlinePlus content, citing sources like `[1]`.
- **Screens every message first.** A keyword check plus a Claude Haiku classifier catch emergency
  and self-harm messages. Those get a fixed, human-written message (call 911 or 988) and never
  reach the answer model. If the screen can't run, CareChat refuses to answer (fails closed).
- **Stays in scope.** No diagnosis, no medicine or dose advice, no off-topic help.

## How it fits together

```
Web app (Next.js) ──> API server (FastAPI) ──> Safety check (Claude Haiku)
                              │                     │ red flag → fixed emergency message
                              │                     ▼ safe
                       Report store ──────────> Answer model (Claude Sonnet, streamed)
                       (SQLite in dev)                ▲
                                          Knowledge base (MedlinePlus, full-text search)
```

| Folder | What's there |
| --- | --- |
| `backend/carechat/` | API server: `safety.py`, `reports.py`, `chat.py`, `knowledge.py`, `prompts.py` |
| `backend/tests/` | Unit and API tests (offline, use a fake Claude client) |
| `backend/evals/` | Safety evaluations that call the real API |
| `backend/scripts/` | MedlinePlus loader |
| `backend/samples/` | Synthetic lab report PDF generator |
| `frontend/` | Next.js chat app |

## Run it locally

You need Python 3.11+, Node 20+, and an Anthropic API key.

```bash
# 1. API server
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m scripts.ingest_medlineplus --urls scripts/lab_test_urls.txt   # load reference pages
uvicorn carechat.main:app --reload --port 8000

# 2. Web app (new terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev        # open http://localhost:3000
```

Make a test report with `python samples/make_sample_report.py samples/sample_lab_report.pdf`
(all values are made up). For all MedlinePlus health topics, download the XML from
https://medlineplus.gov/xml.html and run `python -m scripts.ingest_medlineplus --topics-xml <file>`.
Check MedlinePlus's reuse terms first.

## Tests and evaluations

```bash
cd backend
pytest                              # fast, offline
python -m evals.run_evals safety    # real API: emergency and self-harm detection
python -m evals.run_evals scope     # real API: declines diagnosis, dosing, off-topic (Opus judge)
```

The evaluation sets are a starter (40 safety cases, 15 scope cases). The plan calls for 200
red-flag messages and clinician-reviewed answer accuracy before any pilot.

## Configuration

See `backend/.env.example`. Defaults: answers and report reading use `claude-sonnet-5-5` at effort
`low` (fast chat), the safety screen uses `claude-haiku-5-5`, and server-side refusal fallbacks
(`fallbacks: "default"`) are on. Fallbacks work on the Claude API only; set
`CARECHAT_USE_FALLBACKS=false` on Bedrock or Vertex.

## Before real patients use it

- Sign a BAA with Anthropic (or use Claude through Amazon Bedrock under the AWS BAA) and every other
  vendor that touches health data.
- Move storage to an encrypted database (for example Amazon RDS) and add login (Amazon Cognito).
  The dev SQLite file is not encrypted. Uploaded PDFs are never stored, only extracted results.
- Swap full-text search for PostgreSQL + pgvector if keyword search proves too weak.
- Grow and pass the evaluation sets, and have a clinician review answers.
- Add a consent screen and a "delete my data" flow (report delete exists at `DELETE /api/reports/{id}`).
