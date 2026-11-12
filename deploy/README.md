# Deploying CareChat to Zoho Catalyst

Files for putting CareChat online on Zoho Catalyst (India data centre). The API runs on AppSail and
the web app on Catalyst web client hosting.

The full step-by-step guide, including the Data Store table, environment variables and the hourly
job, is in the [main README](../README.md#put-it-online-on-zoho-catalyst-free-student-tier).

## Build and deploy

From the repository root:

```bash
CARECHAT_API_URL=https://<your-appsail-url> ./deploy/build_catalyst.sh
cd build/catalyst && catalyst deploy
```

On the very first deploy you don't know the AppSail address yet: build with
`CARECHAT_API_URL=https://placeholder`, deploy, then build and deploy again with the real address.

Run `python -m scripts.ingest_medlineplus --urls scripts/lab_test_urls.txt` in `backend/` before
building, so `knowledge.db` ships with the API. Without it, answers have no sources.

## What's here

| File | What it does |
| --- | --- |
| `build_catalyst.sh` | Builds `build/catalyst/`: the API with Linux packages, and the static web app |
| `catalyst/catalyst.json` | Tells the Catalyst CLI what to deploy |
| `catalyst/app.py` | AppSail start file: loads bundled packages and the knowledge base, then starts the API |
| `catalyst/app-config.json` | AppSail settings (Python 3.11, start command) |
| `catalyst/client/client-package.json` | Web client hosting settings |

Copy the `.catalystrc` that `catalyst init` creates into `deploy/catalyst/`. It is ignored by git,
so it is never committed. Set secrets such as `ANTHROPIC_API_KEY` in the Catalyst console, never in
these files.
