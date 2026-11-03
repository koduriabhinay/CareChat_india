# CareChat web app (frontend)

The screens people use: sign-in, consent, family profiles, report upload and summary, chat,
trends, reminders, settings and the admin dashboard. Built with Next.js and Tailwind, and exported
as plain static files so any static host can serve it. It needs the CareChat API from
`../backend` running.

See the [main README](../README.md) for what the app does and how to put it online.

## Run it on your computer

You need Node 20 or newer. Start the API first (see `../backend/README.md`), then:

```bash
cd frontend
npm install
cp .env.example .env.local     # points the app at http://localhost:8000
npm run dev                    # open http://localhost:3000
```

With the API in test mode, use "Test sign-in (no email)" on the sign-in screen.

## Check and build

```bash
npm run lint     # TypeScript type check
npm run build    # static site in out/
```

Settings used at build time:

| Variable | What it does |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Address of the CareChat API |
| `NEXT_PUBLIC_BASE_PATH` | Folder the app is served from, for example `/app` on Catalyst. Empty by default |

`../deploy/build_catalyst.sh` sets both for you when building for Zoho Catalyst.

## What's where

| Path | What it has |
| --- | --- |
| `app/` | One folder per screen (`signin`, `consent`, `profile`, `upload`, `report`, `ask`, `trends`, `reminders`, `print`, `settings`, `admin`, ...) |
| `components/` | Chat, trend chart, values table and shared UI pieces |
| `lib/api.ts` | Calls to the API |
| `lib/i18n.tsx` | Language switching |
| `locales/` | Screen text for 11 languages. Everything except `en.json` is a draft for native speakers to check |
| `public/` | App icon and install manifest |
