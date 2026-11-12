"""CareChat API server."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import chat, reports
from .config import settings
from .knowledge import KnowledgeBase
from .languages import LANGUAGES
from .safety import REGION
from .store import ReportStore

logging.basicConfig(level=logging.INFO)

DISCLAIMER = REGION.disclaimer


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.kb = KnowledgeBase(settings.db_path)
    app.state.reports = ReportStore(settings.db_path, settings.report_retention_hours)

    async def purge_loop() -> None:
        # Expired reports are already unreadable; this also removes them from disk.
        while True:
            await asyncio.sleep(600)
            app.state.reports.purge_expired()

    task = asyncio.create_task(purge_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="CareChat API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "knowledge_passages": request.app.state.kb.count(),
        "disclaimer": DISCLAIMER,
        "region": REGION.code,
        "emergency_number": REGION.emergency_number,
        "crisis_number": REGION.crisis_number,
    }


@app.get("/api/languages")
async def languages() -> list[dict]:
    return [{"code": code, "name": name} for code, name in LANGUAGES.items()]


@app.post("/api/reports")
async def upload_report(request: Request, file: UploadFile = File(...)) -> dict:
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        report = await reports.extract_report(data)
    except reports.ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    report_id = request.app.state.reports.save(report)
    return {"report_id": report_id, "report": report.model_dump(), "disclaimer": DISCLAIMER}


@app.delete("/api/reports/{report_id}")
async def delete_report(request: Request, report_id: str) -> dict:
    if not request.app.state.reports.delete(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    return {"deleted": True}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/api/chat")
async def chat_endpoint(request: Request, body: chat.ChatRequest) -> StreamingResponse:
    problem = chat.validate_request(body)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    report = None
    if body.report_id:
        report = request.app.state.reports.get(body.report_id)
        if report is None:
            raise HTTPException(
                status_code=404,
                detail="Report not found. Reports are deleted after 24 hours, so please upload it again.",
            )

    async def events() -> AsyncIterator[str]:
        async for event in chat.answer(body, report, request.app.state.kb):
            yield _sse(event)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
