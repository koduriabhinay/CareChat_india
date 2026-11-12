# CareChat API (backend)

The CareChat server, written in Python with FastAPI. It reads lab reports with Claude, writes the
plain-language summaries, answers chat questions, screens every message for emergencies, and stores
encrypted health records. The web app in `../frontend` talks to it.

See the [main README](../README.md) for what the app does and how to put it online.

## Set up (once)

You need Python 3.11 or newer.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

## Run it

**Without an API key** (canned answers, no cost):

```bash
python -m scripts.offline_demo     # http://localhost:8000
```

**With real Claude:**

1. Copy `.env.example` to `.env` and fill in at least `ANTHROPIC_API_KEY`,
   `CARECHAT_SECRET_KEY`, `CARECHAT_CRON_TOKEN` and `CARECHAT_ENCRYPTION_KEY`. The file explains
   how to make each one. CareChat reads `.env` by itself when it starts; values already set in
   your terminal take priority.
2. Load the MedlinePlus reference pages once (needs internet, no API key). This makes
   `knowledge.db`:

   ```bash
   python -m scripts.ingest_medlineplus --urls scripts/lab_test_urls.txt
   ```

3. Start the server:

   ```bash
   python -m uvicorn carechat.main:app --reload --port 8000
   ```

   Use `python -m uvicorn`, not plain `uvicorn`, so the `.venv` packages are used even when Conda
   or another Python is active.

Never commit `.env`. It is already in `.gitignore`.

## Tests

```bash
pytest                              # offline, uses a fake Claude client
python -m evals.run_evals safety    # real API: emergency and self-harm detection
python -m evals.run_evals scope     # real API: declines diagnosis, dosing, off-topic
```

## What's where

| Path | What it does |
| --- | --- |
| `carechat/main.py` | Starts the server |
| `carechat/api.py` | All the web routes |
| `carechat/config.py` | Settings, read from `.env` and the environment |
| `carechat/auth.py`, `sms.py`, `mailer.py` | Sign-in by email code, mobile SMS code or Google |
| `carechat/reports.py`, `summary.py`, `results.py` | Reading reports, summaries, low/normal/high, trends, BMI |
| `carechat/chat.py`, `knowledge.py`, `prompts.py` | Chat answers with MedlinePlus sources |
| `carechat/safety.py`, `fixed_messages.json` | Emergency screen and the fixed safety messages in 11 languages |
| `carechat/redact.py` | Removes names and ID numbers before Claude sees anything |
| `carechat/repo.py`, `store.py`, `catalyst_store.py` | Encrypted records, on SQLite locally or Catalyst Data Store online |
| `carechat/jobs.py`, `scheduled.py` | Hourly clean-up, reminders and usage saving |
| `carechat/metrics.py`, `usage.py`, `ratelimit.py` | Admin numbers, Claude spend and limits |
| `scripts/` | MedlinePlus loader and the offline demo |
| `samples/` | A sample lab report PDF to try |
| `tests/`, `evals/` | Offline tests and real-API safety evaluations |
