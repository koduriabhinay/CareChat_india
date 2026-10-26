# CareChat

CareChat helps people in India understand their lab reports in plain language, in their own
language. It explains and teaches. It never diagnoses or prescribes.

**Status:** first version (launch scope). Not for real patients until the steps in
[Before real patients use it](#before-real-patients-use-it) are done.

## What's in this version

- **Report summary.** Take a photo or upload a PDF. Every value appears next to the range printed
  on the report, marked low, normal or high ("range not given on report" when there is none). A
  summary explains the overall picture and each flagged value, and suggests 2-3 questions for the
  doctor. An urgent value shows a fixed emergency message first.
- **Chat** about the report or general health, with sources, voice input and read-aloud (the
  browser's own speech features), and thumbs up/down feedback.
- **11 languages:** English, Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Odia
  and Malayalam, for the app screens, the explanations and the safety messages.
- **Family profiles.** Reports for each person, "whose report is this?" suggested from the printed
  name, a warning when the age or sex on a report doesn't match, and a family view of anything
  flagged.
- **Health form** (all optional): age, sex, height, weight (BMI with the Indian cut-offs, weight
  over time), conditions, medicines, pregnancy and diet (vegetarian, eggetarian, non-vegetarian,
  vegan, Jain). Asked again every 3 months.
- **History and trends** (opt-in): a timeline, a chart per test, changes worked out in code, a
  "since the last report" view and "show this to your doctor soon" for big changes.
- **Sign-in** with an Indian mobile number (SMS code), Google or an emailed code, or try without
  an account. Doctor-ready summary
  (print or save as PDF), CSV download, reminders you set yourself (in the app and by email).
- **Privacy:** consent screens with nothing pre-ticked (recorded with the notice version), adults
  only, black-out tool for photos, names and ID numbers removed before Claude reads anything,
  health data encrypted at rest, reports deleted after 24 hours unless history is on, one-tap
  delete of everything.
- **Admin dashboard:** active people by level and language, reports and chats per day, Claude
  spend against the monthly limit, safety triggers, feedback, errors and response times. Counts
  only, never names next to health values.
- **Cost limits:** a monthly Claude budget (new work stops when it is reached) and daily limits per
  person.

Left for a later phase: the doctor case portal, learning tools (quizzes, guess-then-reveal) and the
verification and case review queues.

## How it fits together

```
Web app (Next.js, static files) ──> API (FastAPI on Zoho Catalyst AppSail) ──> Claude API
                                          │                                     (Sonnet: reading,
                                          ├─ Data Store (encrypted records)       summaries, answers;
                                          ├─ Knowledge base (MedlinePlus, SQLite)  Haiku: safety screen)
                                          └─ Email (Zoho Mail SMTP)
```

| Folder | What's there |
| --- | --- |
| `backend/carechat/` | API: `api.py` (routes), `reports.py`, `summary.py`, `results.py` (status, trends, BMI), `safety.py`, `chat.py`, `repo.py` (records and retention), `catalyst_store.py` |
| `backend/tests/` | Offline tests with a fake Claude client |
| `backend/evals/` | Safety evaluations that call the real API |
| `backend/scripts/` | MedlinePlus loader, offline demo server |
| `frontend/` | Web app; `locales/` holds the screen text per language |
| `deploy/` | Zoho Catalyst config and build script |

## Try it on your computer (no API key needed)

You need Python 3.11+ and Node 20+.

```bash
# 1. API with a stand-in for Claude (canned answers, no cost)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.offline_demo          # http://localhost:8000

# 2. Web app (new terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev                             # open http://localhost:3000
```

Sign in with any email using "Test sign-in". To see the admin dashboard, start the API with
`CARECHAT_ADMIN_EMAILS=you@example.com`.

To use real Claude, copy `backend/.env.example` to `backend/.env`, fill it in, load the reference
pages once, and run the real server. Run these inside the `.venv` you made above:

```bash
cd backend
source .venv/bin/activate
python -m scripts.ingest_medlineplus --urls scripts/lab_test_urls.txt
set -a && source .env && set +a          # loads your API key and settings
python -m uvicorn carechat.main:app --reload --port 8000
```

Use `python -m uvicorn`, not plain `uvicorn`: with Conda (or another Python) active, plain
`uvicorn` can start a different Python that doesn't have CareChat's packages, and fails with
"No module named 'httpx'".

## Put it online on Zoho Catalyst (free student tier)

The Claude API is the only paid service. Everything else runs on Catalyst's free tier in the India
data centre.

### What you need

1. **Anthropic API key** from console.anthropic.com. Set a monthly spend limit there too
   (Settings > Limits), as a second guard behind CareChat's own budget.
2. **Zoho account** with Catalyst, created in the **India data centre** (catalyst.zoho.in).
3. **Catalyst CLI:** `npm install -g zcatalyst-cli`, then `catalyst login`.
4. **A GitHub repository** for this code (optional but recommended). A workflow in
   `.github/workflows/ci.yml` runs the tests on every push.
5. Optional: a **Google OAuth client id** (Google Cloud console > APIs & Services > Credentials >
   OAuth client, type Web) for "Sign in with Google", and a **Zoho Mail** address with an app
   password for sign-in codes and reminder emails.
6. Optional: a **Message Central** account for mobile number sign-in
   (https://console.messagecentral.com/signup, email and password, no card). It sends the SMS
   codes on its own registered template, so you don't need TRAI DLT registration. Each code costs
   about ₹0.20; new accounts get free test credits. Copy the **Customer ID** from its console.

### Steps

1. **Create the project.** In the Catalyst console, create a project (for example `carechat`). In
   an empty folder run `catalyst init`, pick the project, and note the `.catalystrc` it creates.
   Copy that `.catalystrc` into `deploy/catalyst/`.
2. **Create the Data Store table.** Cloud Scale > Data Store > Create table `records` with these
   columns:

   | Column | Type |
   | --- | --- |
   | doc_id | Var Char (64), unique |
   | collection | Var Char (32) |
   | account_id | Var Char (64) |
   | profile_id | Var Char (64) |
   | ref_id | Var Char (64) |
   | created_at | Var Char (32) |
   | expires_at | Var Char (32) |
   | data | Text |

   Give the AppSail service read, write and delete permission on it (the table's Scopes and
   Permissions page).
3. **Load the knowledge base** on your computer (needs internet, no API key):
   `cd backend && python -m scripts.ingest_medlineplus --urls scripts/lab_test_urls.txt`.
   This makes `backend/knowledge.db`, which ships with the API.
4. **First deploy of the API**, to get its address: run
   `CARECHAT_API_URL=https://placeholder ./deploy/build_catalyst.sh`, then
   `cd build/catalyst && catalyst deploy`. The CLI prints the AppSail URL (like
   `https://carechatapi-6xxxxxxxx.development.catalystappsail.in`) and the web client URL (like
   `https://carechat-6xxxxxxxx.development.catalystserverless.in/app/`).
5. **Set the environment variables** on the AppSail service (console > AppSail > carechatapi >
   Configuration). Use `backend/.env.example` as the list. At minimum:
   - `ANTHROPIC_API_KEY`
   - `CARECHAT_SECRET_KEY`, `CARECHAT_CRON_TOKEN`, `CARECHAT_ENCRYPTION_KEY` (the file shows how to
     make each; keep a safe copy of the encryption key, because losing it makes saved data
     unreadable)
   - `CARECHAT_AUTH_MODE=prod`
   - `CARECHAT_ADMIN_EMAILS` (your email)
   - `CARECHAT_ALLOWED_ORIGINS` and `CARECHAT_APP_URL`: the web client URL without `/app/`, for
     example `https://carechat-6xxxxxxxx.development.catalystserverless.in`
   - `CARECHAT_MAIL=smtp` plus the SMTP settings, and `CARECHAT_GOOGLE_CLIENT_ID` if you use them
   - `CARECHAT_MONTHLY_BUDGET_USD` (for example 10)
   - For mobile sign-in: `CARECHAT_SMS=messagecentral`, `CARECHAT_MC_CUSTOMER_ID`,
     `CARECHAT_MC_PASSWORD` and `CARECHAT_DAILY_SMS_CAP` (codes per day in total, for example 100,
     which caps SMS spend at about ₹20 a day). Without them, mobile sign-in stays hidden.
6. **Rebuild with the real API address and deploy again:**
   `CARECHAT_API_URL=https://carechatapi-6xxxxxxxx.development.catalystappsail.in ./deploy/build_catalyst.sh`
   then `cd build/catalyst && catalyst deploy`.
7. **Hourly job.** In the console, Job Scheduling (Cron) > create a cron that runs every hour and
   calls a URL: `POST <AppSail URL>/api/internal/hourly` with header `X-Cron-Token: <your cron
   token>`. It deletes expired data, saves usage numbers and sends reminder emails. (While the API
   is awake it also does this itself, but AppSail sleeps when idle.)
8. **Google sign-in (optional):** add the web client URL to the OAuth client's "Authorised
   JavaScript origins".
9. **Check it:** open the web client URL, sign in, accept, add yourself, upload
   `backend/samples/sample_lab_report.pdf`.

If Catalyst serves the web app at the root of a domain instead of `/app` (Slate or a custom
domain), build with `CARECHAT_BASE_PATH=""`.

### Free tier limits that matter

- Data Store: 2 GB and limited reads and writes a month. CareChat caches reads in memory and saves
  usage numbers once an hour to stay well inside them. Watch Usage in the console as people join.
- AppSail: one request may take up to 30 seconds and the service sleeps after a few idle minutes,
  so the first request after a pause is slow. Report reading runs in the background for this
  reason.
- The API keeps rate limits, sign-in codes and the read cache in memory, so run one instance.

## Tests and evaluations

```bash
cd backend
pytest                              # offline tests
python -m evals.run_evals safety    # real API: emergency and self-harm detection
python -m evals.run_evals scope     # real API: declines diagnosis, dosing, off-topic
```

## Before real patients use it

These are engineering notes, not legal advice.

- **Clinician review of the safety messages.** The emergency, self-harm, urgent-value and
  disclaimer texts in all 10 Indian languages (`backend/carechat/fixed_messages.json`) are drafts.
  A native-speaking clinician must check each one. Known doubts: "faint" and "confused" in the
  urgent-value message, Telugu "can't", Odia loanwords, and how the Urdu numbers display.
- **Screen translations** in `frontend/locales/` are drafts too; have native speakers check them.
- **Urgent-value limits** in `backend/carechat/results.py` and the "big change" threshold (30%) are
  starting values for a clinician to set.
- **Privacy notice and terms** (in `frontend/locales/en.json`) need a lawyer's review, a named
  grievance officer, and Anthropic's data processing terms signed. DPDP Act 2023 and Rules apply.
- **Stay educational.** Software that diagnoses or recommends treatment can count as a medical
  device under CDSCO rules.
- **Evaluation.** Grow the evaluation sets with more Indian-language cases and real Indian report
  layouts, and have a clinician review a sample of answers (the admin page collects
  thumbs-down answers for this).
