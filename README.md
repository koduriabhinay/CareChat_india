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
  and self-harm messages, including Hindi and Hinglish. Those get a fixed, human-written message
  (call 112, or Tele-MANAS on 14416) and never reach the answer model. If the screen can't run, CareChat refuses to answer (fails closed).
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

The evaluation sets are a starter (46 safety cases including Hindi and Hinglish, 15 scope cases). The plan calls for 200
red-flag messages and clinician-reviewed answer accuracy before any pilot.

## Configuration

See `backend/.env.example`. The launch region is India (`CARECHAT_REGION=IN`): emergency
messages use 112 (108 for an ambulance) and Tele-MANAS (14416). `CARECHAT_REGION=US` switches to
911 and 988. Re-check every number against official sources before launch. Other defaults: answers and report reading use `claude-sonnet-5-5` at effort
`low` (fast chat), the safety screen uses `claude-haiku-5-5`, and server-side refusal fallbacks
(`fallbacks: "default"`) are on. Fallbacks work on the Claude API only; set
`CARECHAT_USE_FALLBACKS=false` on Bedrock or Vertex.

## Before real patients use it (India launch)

These are engineering notes, not legal advice. Have a lawyer familiar with Indian health and data
law review the launch.

- **DPDP Act 2023 and DPDP Rules 2025.** CareChat is a data fiduciary. It needs a clear consent
  notice in plain language (and in the user's language), a way to withdraw consent and delete data,
  breach reporting to the Data Protection Board and affected users, and a named contact for
  grievances. Users under 18 need verifiable parental consent, so either verify age or block minors.
- **Hosting.** Use an India region such as AWS Mumbai (ap-south-1). The DPDP Act does not require
  data to stay in India today, but check where Claude processes requests and record it in the
  privacy notice. Sign Anthropic's data processing terms.
- **Stay educational.** Software that diagnoses or recommends treatment can count as a medical
  device under CDSCO rules, and only registered medical practitioners may give consultations under
  the Telemedicine Practice Guidelines. CareChat must keep explaining, never diagnosing or
  prescribing.
- **Storage and login.** Move to an encrypted database and add login. The dev SQLite file is not
  encrypted. Uploaded PDFs are never stored, only extracted results.
- **Content.** MedlinePlus is US content; consider adding Indian public sources and checking that
  advice fits Indian care settings. Test with real Indian lab report layouts.
- **Evaluation.** Grow and pass the evaluation sets, with more Hindi and regional-language cases,
  and have a clinician review answers.
