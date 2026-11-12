"""CareChat API server.

Runs locally with uvicorn, and on Zoho Catalyst AppSail (see catalyst/README).
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import api
from .config import settings
from .knowledge import KnowledgeBase
from .metrics import metrics
from .repo import Repo
from .scheduled import run_hourly
from .store import build_store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = Repo(build_store(settings))
    app.state.repo = repo
    app.state.kb = KnowledgeBase(settings.knowledge_path)
    try:
        month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        metrics.load_month(repo.metrics_since(month_start))
    except Exception:  # the app still starts if saved metrics can't be read
        log.exception("Could not load this month's usage")

    task = None
    if settings.run_inprocess_jobs:
        async def hourly_loop() -> None:
            # Backup for the Catalyst cron; the reminder guard stops double emails.
            while True:
                await asyncio.sleep(3600)
                await run_hourly(repo)

        task = asyncio.create_task(hourly_loop())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    with suppress(Exception):
        snap = metrics.roll()
        if snap:
            repo.save_metrics(snap)


app = FastAPI(title="CareChat API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def catalyst_headers(request: Request, call_next):
    if settings.store_backend == "catalyst":
        from .catalyst_store import remember_request_headers

        remember_request_headers(request.headers)
    return await call_next(request)


app.include_router(api.router)


def run() -> None:
    """Entry point for AppSail: it passes the port in X_ZOHO_CATALYST_LISTEN_PORT."""
    import uvicorn

    port = int(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT") or os.getenv("PORT") or 8000)
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True)


if __name__ == "__main__":
    run()
