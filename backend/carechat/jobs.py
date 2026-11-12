"""Background work: reading an uploaded report, and the hourly jobs.

Report reading runs after the upload request has already returned, so it
never runs into AppSail's 30-second request limit. The web app checks back
for the result. The file itself only lives in memory while it is read.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from . import reports
from .knowledge import KnowledgeBase
from .metrics import metrics
from .redact import printed_name
from .repo import Repo, age_from_birth_year
from .results import table_rows
from .store import Record
from .summary import SummaryError, write_summary

log = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def run_in_background(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def profile_facts(profile: dict[str, Any] | None) -> dict[str, Any]:
    """The optional health-form details that help explanations fit the person."""
    if not profile:
        return {}
    facts = {
        "age": age_from_birth_year(profile.get("birth_year")),
        "sex": profile.get("sex"),
        "diet_type": profile.get("diet_type"),
        "pregnant": "yes" if profile.get("pregnant") else None,
        "conditions": profile.get("conditions") or [],
        "medicines": profile.get("medicines") or [],
    }
    return {k: v for k, v in facts.items() if v not in (None, "", [])}


def person_text(profile: dict[str, Any] | None) -> str | None:
    facts = profile_facts(profile)
    if not facts:
        return None
    return "\n".join(f"{k.replace('_', ' ').capitalize()}: {', '.join(v) if isinstance(v, list) else v}"
                     for k, v in facts.items())


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", name.lower()) if len(t) >= 3}


def suggest_profile(name: str | None, profiles: list[Record]) -> str | None:
    """Match the printed patient name to a family profile's 'name on reports'."""
    if not name:
        return None
    wanted = _tokens(name)
    best, best_score = None, 0
    for p in profiles:
        have = _tokens(p.data.get("name_on_reports") or "") | _tokens(p.data.get("display_name") or "")
        score = len(wanted & have)
        if score > best_score:
            best, best_score = p.id, score
    return best


def mismatch(report: reports.Report, profile: dict[str, Any] | None) -> list[str]:
    """Reasons this report may belong to someone else: printed age or sex don't fit the profile."""
    if not profile:
        return []
    problems = []
    age = age_from_birth_year(profile.get("birth_year"))
    if report.patient_age and age is not None:
        m = re.search(r"\d+", report.patient_age)
        if m and abs(int(m.group()) - age) > 2:
            problems.append("age")
    sex = profile.get("sex")
    if report.patient_sex and sex in ("male", "female") and report.patient_sex != sex:
        problems.append("sex")
    return problems


async def read_report(
    repo: Repo, kb: KnowledgeBase, report_id: str, account_id: str, data: bytes, kind: str, media: str,
    language: str | None,
) -> None:
    rec = repo.report(account_id, report_id)
    if rec is None:
        return
    profiles = repo.profiles(account_id)
    profile = next((p for p in profiles if p.id == rec.profile_id), None)
    known_names = [n for p in profiles for n in (p.data.get("name_on_reports"), p.data.get("display_name")) if n]
    try:
        if kind == "pdf":
            raw, redacted = reports.prepare_pdf_text(data, known_names)
            rec.data["suggested_profile_id"] = suggest_profile(printed_name(raw), profiles)
            del raw
            extracted = await reports.extract_from_text(redacted, known_names)
        else:
            extracted = await reports.extract_from_image(data, media, known_names)
    except reports.ReportError as exc:
        metrics.event("report_failed")
        rec.data.update(status="failed", error=str(exc), error_code=exc.code)
        repo.save_report(rec)
        return
    except Exception:  # never leave a report stuck in "reading"
        log.exception("Report reading failed")
        metrics.event("report_failed")
        rec.data.update(status="failed", error="Something went wrong while reading. Please try again.",
                        error_code="server")
        repo.save_report(rec)
        return
    finally:
        del data

    rows = table_rows([r.model_dump() for r in extracted.results])
    rec.data.update(
        report_type=extracted.report_type, report_date=extracted.report_date, patient_age=extracted.patient_age,
        patient_sex=extracted.patient_sex, rows=rows, other_findings=extracted.other_findings,
        critical=any(r["critical"] for r in rows),
        mismatch=mismatch(extracted, profile.data if profile else None),
    )
    try:
        summary, passages = await write_summary(
            rows, extracted.report_type, language, profile_facts(profile.data if profile else None), kb
        )
        rec.data["summary"] = summary.model_dump()
        rec.data["sources"] = [{"index": i, "title": p.title, "url": p.url} for i, p in enumerate(passages, start=1)]
    except SummaryError:
        log.exception("Summary failed")
        rec.data["summary"] = None
    rec.data["status"] = "ready"
    rec.data["read_at"] = datetime.now(timezone.utc).isoformat()
    repo.save_report(rec)
    metrics.event("report_ready")
    if rec.data["critical"]:
        metrics.event("report_critical")
