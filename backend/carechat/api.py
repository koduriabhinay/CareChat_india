"""CareChat's HTTP API: patients, sign-in, reports, chat, trends, reminders, admin."""

from __future__ import annotations

import csv
import hmac
import io
import json
import re
import time
from collections import Counter
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import AfterValidator, BaseModel, Field
from typing import Annotated

from . import auth, chat, mailer, reports, sms
from .auth import Principal, current_principal, require_admin, require_member
from .config import settings
from .jobs import person_text, run_in_background, read_report
from .languages import LANGUAGES
from .metrics import metrics, summarize
from .ratelimit import limits
from .repo import NOTICE_VERSION, Repo, age_from_birth_year
from .results import bmi, build_trends, parse_report_date
from .safety import REGION
from .scheduled import run_hourly
from .store import Record, iso, now

router = APIRouter(prefix="/api")

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def _check_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL_RE.match(value):
        raise ValueError("Please enter a valid email address.")
    return value


EmailStr = Annotated[str, AfterValidator(_check_email)]

BUDGET_MESSAGE = "CareChat has reached its limit for this month, so it can't read reports or answer right now. Please try again later."


def repo_of(request: Request) -> Repo:
    return request.app.state.repo


def load_account(request: Request, principal: Principal) -> Record:
    account = repo_of(request).account(principal.account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    metrics.active(principal.account_id, principal.role, account.data.get("ui_language"))
    return account


def need_consent(request: Request, account: Record) -> None:
    if not repo_of(request).has_processing_consent(account.id):
        raise HTTPException(status_code=403, detail="Please read and accept the privacy notice first.")


def _lang(code: str | None) -> str:
    return code if code in LANGUAGES else "en"


# --- meta ---------------------------------------------------------------------------

@router.get("/health")
async def health(request: Request, language: str | None = None) -> dict:
    lang = _lang(language)
    return {
        "status": "ok",
        "knowledge_passages": request.app.state.kb.count(),
        "disclaimer": REGION.text("disclaimer", lang),
        "region": REGION.code,
        "emergency_number": REGION.emergency_number,
        "ambulance_number": REGION.ambulance_number,
        "crisis_number": REGION.crisis_number,
        "crisis_line_name": REGION.crisis_line_name,
        "google_client_id": settings.google_client_id or None,
        "phone_sign_in": sms.enabled(),
        "dev_auth": settings.dev_auth,
        "notice_version": NOTICE_VERSION,
    }


@router.get("/languages")
async def languages() -> list[dict]:
    return [{"code": code, "name": name} for code, name in LANGUAGES.items()]


# --- sign-in ----------------------------------------------------------------------

class GuestIn(BaseModel):
    language: str | None = None


class EmailStartIn(BaseModel):
    email: EmailStr


class EmailVerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)
    guest_token: str | None = None
    language: str | None = None


class GoogleIn(BaseModel):
    id_token: str
    guest_token: str | None = None
    language: str | None = None


class DevIn(BaseModel):
    email: EmailStr
    guest_token: str | None = None
    language: str | None = None


def _session(account: Record) -> dict:
    principal = Principal(account_id=account.id, role=account.data.get("role", "patient"), email=account.data.get("email"))
    days = settings.report_retention_hours / 24 if account.data.get("guest") else None
    return {"token": auth.issue_token(principal, days), "role": principal.role}


def _sign_in(request: Request, email: str, guest_token: str | None, language: str | None) -> dict:
    repo = repo_of(request)
    is_new = repo.account_by_email(email) is None
    account = repo.get_or_create_member(email, auth.role_for_email(email), language=_lang(language))
    return _finish_sign_in(request, account, is_new, guest_token)


def _finish_sign_in(request: Request, account: Record, is_new: bool, guest_token: str | None) -> dict:
    repo = repo_of(request)
    if is_new:
        metrics.event("signups")
    if guest_token:
        guest = auth.read_token(guest_token)
        if guest and guest.is_guest:
            repo.claim_guest(guest.account_id, account)
    repo.audit(account.id, account.data["role"], "signed_in")
    return _session(account)


@router.post("/auth/guest")
async def guest(request: Request, body: GuestIn) -> dict:
    account = repo_of(request).create_guest(_lang(body.language))
    metrics.event("guests")
    return _session(account)


@router.post("/auth/email/start")
async def email_start(body: EmailStartIn) -> dict:
    if not limits.take(body.email.lower(), "email_code", 5):
        raise HTTPException(status_code=429, detail="Too many codes today. Please try again tomorrow.")
    code = auth.new_email_code(body.email)
    await mailer.send_email(
        body.email, "Your CareChat sign-in code",
        f"Your CareChat sign-in code is {code}. It works for 10 minutes.\n\nIf you didn't ask for it, ignore this email.",
    )
    out: dict[str, Any] = {"sent": True}
    if settings.dev_auth and settings.mail_backend == "console":
        out["dev_code"] = code  # local testing only
    return out


@router.post("/auth/email/verify")
async def email_verify(request: Request, body: EmailVerifyIn) -> dict:
    if not auth.check_email_code(body.email, body.code):
        raise HTTPException(status_code=400, detail="That code is wrong or has expired.")
    return _sign_in(request, body.email, body.guest_token, body.language)


class PhoneStartIn(BaseModel):
    phone: str = Field(max_length=20)


class PhoneVerifyIn(BaseModel):
    phone: str = Field(max_length=20)
    code: str = Field(min_length=4, max_length=10)
    guest_token: str | None = None
    language: str | None = None


def _phone(raw: str) -> str:
    phone = sms.normalize_phone(raw)
    if not phone:
        raise HTTPException(status_code=422, detail="Please enter a 10-digit Indian mobile number.")
    return phone


@router.post("/auth/phone/start")
async def phone_start(request: Request, body: PhoneStartIn) -> dict:
    if not sms.enabled():
        raise HTTPException(status_code=404, detail="Mobile number sign-in isn't available. Please use email.")
    phone = _phone(body.phone)
    ip = request.client.host if request.client else "unknown"
    # Each SMS costs money: limit per number, per network address, and in total each day.
    if limits.used("all", "sms") >= settings.daily_sms_cap:
        raise HTTPException(status_code=429, detail="Mobile sign-in is busy today. Please use email or Google instead.")
    if not limits.take(phone, "sms", 3) or not limits.take(ip, "sms_ip", 10):
        raise HTTPException(status_code=429, detail="Too many codes today. Please try again tomorrow or use email.")
    try:
        code = await sms.send_code(phone)
    except sms.SmsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    limits.take("all", "sms", settings.daily_sms_cap)
    metrics.event("sms_sent")
    out: dict[str, Any] = {"sent": True, "phone": phone}
    if code and settings.dev_auth:
        out["dev_code"] = code  # local testing only
    return out


@router.post("/auth/phone/verify")
async def phone_verify(request: Request, body: PhoneVerifyIn) -> dict:
    phone = _phone(body.phone)
    if not await sms.check_code(phone, body.code):
        raise HTTPException(status_code=400, detail="That code is wrong or has expired.")
    repo = repo_of(request)
    is_new = repo.account_by_phone(phone) is None
    account = repo.get_or_create_phone_member(phone, _lang(body.language))
    return _finish_sign_in(request, account, is_new, body.guest_token)


@router.post("/auth/google")
async def google(request: Request, body: GoogleIn) -> dict:
    email = await auth.verify_google_token(body.id_token)
    if not email:
        raise HTTPException(status_code=400, detail="Google sign-in didn't work. Please try again.")
    return _sign_in(request, email, body.guest_token, body.language)


@router.post("/auth/dev")
async def dev_sign_in(request: Request, body: DevIn) -> dict:
    if not settings.dev_auth:
        raise HTTPException(status_code=404)
    return _sign_in(request, body.email, body.guest_token, body.language)


# --- me, consent, settings --------------------------------------------------------

def _me(request: Request, account: Record) -> dict:
    repo = repo_of(request)
    consents = repo.consents(account.id)
    return {
        "id": account.id,
        "role": account.data.get("role"),
        "guest": bool(account.data.get("guest")),
        "email": account.data.get("email"),
        "phone": account.data.get("phone"),
        "ui_language": account.data.get("ui_language", "en"),
        "history_enabled": bool(account.data.get("history_enabled")),
        "reminder_emails": bool(account.data.get("reminder_emails", True)),
        "consents": consents,
        "needs_consent": not repo.has_processing_consent(account.id),
        "notice_version": NOTICE_VERSION,
        "usage_today": {"reports": limits.used(account.id, "report"), "questions": limits.used(account.id, "question")},
        "daily_caps": {"reports": settings.daily_reports_per_user, "questions": settings.daily_questions_per_user},
    }


@router.get("/me")
async def me(request: Request, principal: Principal = Depends(current_principal)) -> dict:
    return _me(request, load_account(request, principal))


class MeIn(BaseModel):
    ui_language: str | None = None
    reminder_emails: bool | None = None


@router.patch("/me")
async def update_me(request: Request, body: MeIn, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    if body.ui_language is not None:
        account.data["ui_language"] = _lang(body.ui_language)
    if body.reminder_emails is not None:
        account.data["reminder_emails"] = body.reminder_emails
    repo_of(request).update_account(account)
    return _me(request, account)


class ConsentIn(BaseModel):
    processing: bool
    terms: bool
    adult: bool
    history: bool = False
    language: str | None = None


@router.post("/consents")
async def give_consent(request: Request, body: ConsentIn, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    repo = repo_of(request)
    if not (body.processing and body.terms):
        raise HTTPException(status_code=400, detail="CareChat needs your consent to read reports and answer.")
    if not body.adult:
        raise HTTPException(status_code=403, detail="CareChat is for adults 18 and over for now.")
    for purpose in ("processing", "terms", "adult"):
        repo.record_consent(account.id, purpose, True, body.language)
    if body.history and not account.data.get("guest"):
        repo.record_consent(account.id, "history", True, body.language)
        repo.set_history(account, True)
    metrics.event("consents_given")
    return _me(request, account)


class HistoryIn(BaseModel):
    enabled: bool
    language: str | None = None


@router.post("/me/history")
async def set_history(request: Request, body: HistoryIn, principal: Principal = Depends(require_member)) -> dict:
    account = load_account(request, principal)
    repo = repo_of(request)
    repo.record_consent(account.id, "history", body.enabled, body.language)
    repo.set_history(account, body.enabled)
    repo.audit(account.id, principal.role, "history_on" if body.enabled else "history_off_deleted")
    metrics.event("history_on" if body.enabled else "history_off")
    return _me(request, account)


@router.delete("/me")
async def delete_me(request: Request, principal: Principal = Depends(current_principal)) -> dict:
    repo = repo_of(request)
    load_account(request, principal)
    repo.record_consent(principal.account_id, "processing", False, None)
    n = repo.delete_account(principal.account_id)
    repo.audit(principal.account_id, principal.role, "deleted_account", f"{n} records")
    metrics.event("accounts_deleted")
    return {"deleted": True}


# --- profiles (family) --------------------------------------------------------------

Sex = Literal["male", "female", "other"]
Diet = Literal["vegetarian", "eggetarian", "non_vegetarian", "vegan", "jain"]


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    relation: str = Field(default="self", max_length=30)
    language: str | None = None
    name_on_reports: str | None = Field(default=None, max_length=100)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: Sex | None = None
    height_cm: float | None = Field(default=None, ge=30, le=250)
    weight_kg: float | None = Field(default=None, ge=1, le=400)
    conditions: list[str] = Field(default_factory=list, max_length=20)
    medicines: list[str] = Field(default_factory=list, max_length=30)
    pregnant: bool = False
    diet_type: Diet | None = None
    diet_notes: str | None = Field(default=None, max_length=500)
    family_consent: bool = False


def _profile_out(rec: Record, reports_for: list[Record] | None = None) -> dict:
    d = rec.data
    weights = d.get("weights") or []
    latest_weight = weights[-1]["kg"] if weights else None
    out = {
        "id": rec.id,
        **{k: d.get(k) for k in ("display_name", "relation", "language", "name_on_reports", "birth_year", "sex",
                                 "height_cm", "conditions", "medicines", "pregnant", "diet_type", "diet_notes",
                                 "is_self", "health_updated_at")},
        "age": age_from_birth_year(d.get("birth_year")),
        "weights": weights,
        "weight_kg": latest_weight,
        "bmi": bmi(d.get("height_cm"), latest_weight),
        "health_form_due": _form_due(d.get("health_updated_at")),
    }
    if reports_for is not None:
        ready = [r for r in reports_for if r.data.get("status") == "ready"]
        latest = max(ready, key=lambda r: r.created_at, default=None)
        out["report_count"] = len(ready)
        out["latest_report"] = None if latest is None else {
            "id": latest.id, "report_type": latest.data.get("report_type"), "report_date": latest.data.get("report_date"),
            "flagged": sum(1 for r in latest.data.get("rows", []) if r["status"] in ("low", "high", "abnormal", "critical")),
            "critical": bool(latest.data.get("critical")), "created_at": latest.created_at,
        }
    return out


def _form_due(updated: str | None) -> bool:
    if not updated:
        return True
    try:
        return datetime.fromisoformat(updated.replace("Z", "+00:00")) < datetime.now(timezone.utc) - timedelta(days=90)
    except ValueError:
        return True


def _apply_profile(rec: Record, body: ProfileIn) -> None:
    d = rec.data
    for key in ("display_name", "relation", "name_on_reports", "birth_year", "sex", "height_cm", "pregnant",
                "diet_type", "diet_notes"):
        d[key] = getattr(body, key)
    d["language"] = _lang(body.language) if body.language else d.get("language")
    d["conditions"] = [c.strip()[:80] for c in body.conditions if c.strip()]
    d["medicines"] = [m.strip()[:80] for m in body.medicines if m.strip()]
    if body.weight_kg:
        weights = d.setdefault("weights", [])
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not weights or weights[-1]["kg"] != body.weight_kg:
            weights.append({"date": today, "kg": body.weight_kg})
            del weights[:-60]
    d["health_updated_at"] = iso(now())


@router.get("/profiles")
async def list_profiles(request: Request, principal: Principal = Depends(current_principal)) -> list[dict]:
    account = load_account(request, principal)
    repo = repo_of(request)
    all_reports = repo.reports(account.id)
    return [_profile_out(p, [r for r in all_reports if r.profile_id == p.id]) for p in repo.profiles(account.id)]


@router.post("/profiles")
async def create_profile(request: Request, body: ProfileIn, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    need_consent(request, account)
    repo = repo_of(request)
    existing = repo.profiles(account.id)
    is_self = body.relation == "self"
    if is_self and any(p.data.get("is_self") for p in existing):
        raise HTTPException(status_code=400, detail="You already have your own profile.")
    if is_self and body.birth_year and (age_from_birth_year(body.birth_year) or 0) < 18:
        raise HTTPException(status_code=403, detail="CareChat is for adults 18 and over for now.")
    if not is_self and not body.family_consent:
        raise HTTPException(status_code=400, detail="Please confirm this person agreed to you managing their reports.")
    if len(existing) >= 20:
        raise HTTPException(status_code=400, detail="That's the most profiles one account can have.")
    rec = Record(collection="profile", data={"is_self": is_self})
    _apply_profile(rec, body)
    rec = repo.create_profile(account, rec.data)
    if not is_self:
        repo.record_consent(account.id, "family", True, body.language, profile_id=rec.id)
    return _profile_out(rec, [])


def _owned_profile(request: Request, account: Record, profile_id: str) -> Record:
    rec = repo_of(request).profile(account.id, profile_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return rec


@router.get("/profiles/{profile_id}")
async def get_profile(request: Request, profile_id: str, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    rec = _owned_profile(request, account, profile_id)
    return _profile_out(rec, repo_of(request).reports(account.id, profile_id))


@router.put("/profiles/{profile_id}")
async def update_profile(request: Request, profile_id: str, body: ProfileIn,
                         principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    rec = _owned_profile(request, account, profile_id)
    body.relation = "self" if rec.data.get("is_self") else (body.relation if body.relation != "self" else rec.data.get("relation", "family"))
    if rec.data.get("is_self") and body.birth_year and (age_from_birth_year(body.birth_year) or 0) < 18:
        raise HTTPException(status_code=403, detail="CareChat is for adults 18 and over for now.")
    _apply_profile(rec, body)
    repo_of(request).save_profile(rec)
    return _profile_out(rec, repo_of(request).reports(account.id, profile_id))


@router.delete("/profiles/{profile_id}")
async def delete_profile(request: Request, profile_id: str, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    _owned_profile(request, account, profile_id)
    n = repo_of(request).delete_profile(account.id, profile_id)
    repo_of(request).audit(account.id, principal.role, "deleted_profile", f"{n} records")
    return {"deleted": True}


# --- reports ------------------------------------------------------------------------

def _report_out(rec: Record, full: bool = True) -> dict:
    d = rec.data
    out = {
        "id": rec.id, "profile_id": rec.profile_id, "status": d.get("status"), "source": d.get("source"),
        "error": d.get("error"), "error_code": d.get("error_code"), "report_type": d.get("report_type"),
        "report_date": d.get("report_date"), "created_at": rec.created_at, "expires_at": rec.expires_at,
        "critical": bool(d.get("critical")), "language": d.get("language"),
        "flagged": sum(1 for r in d.get("rows", []) if r["status"] in ("low", "high", "abnormal", "critical")),
    }
    if full:
        out.update({
            "rows": d.get("rows", []), "summary": d.get("summary"), "sources": d.get("sources", []),
            "other_findings": d.get("other_findings", []), "mismatch": d.get("mismatch", []),
            "patient_age": d.get("patient_age"), "patient_sex": d.get("patient_sex"),
            "suggested_profile_id": d.get("suggested_profile_id"),
            "critical_message": REGION.text("critical_value", d.get("language")) if d.get("critical") else None,
        })
    return out


@router.post("/reports")
async def upload_report(
    request: Request,
    file: UploadFile = File(...),
    profile_id: str = Form(...),
    language: str | None = Form(default=None),
    principal: Principal = Depends(current_principal),
) -> dict:
    account = load_account(request, principal)
    need_consent(request, account)
    repo = repo_of(request)
    profile = _owned_profile(request, account, profile_id)
    if metrics.over_budget():
        raise HTTPException(status_code=503, detail=BUDGET_MESSAGE)
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        kind, media = reports.detect_kind(data)
    except reports.ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not limits.take(account.id, "report", settings.daily_reports_per_user):
        raise HTTPException(status_code=429, detail="You've reached today's limit for reports. Please try again tomorrow.")
    lang = _lang(language or profile.data.get("language") or account.data.get("ui_language"))
    rec = repo.create_report(account, profile.id, {"status": "reading", "source": kind, "language": lang})
    metrics.event("reports_uploaded")
    metrics.event(f"reports_{kind}")
    run_in_background(read_report(repo, request.app.state.kb, rec.id, account.id, data, kind, media, lang))
    return _report_out(rec)


@router.get("/reports")
async def list_reports(request: Request, profile_id: str | None = None,
                       principal: Principal = Depends(current_principal)) -> list[dict]:
    account = load_account(request, principal)
    recs = repo_of(request).reports(account.id, profile_id)
    return [_report_out(r, full=False) for r in sorted(recs, key=lambda r: r.created_at, reverse=True)]


def _owned_report(request: Request, account: Record, report_id: str) -> Record:
    rec = repo_of(request).report(account.id, report_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="Report not found. Without saved history, reports are deleted after 24 hours.",
        )
    return rec


@router.get("/reports/{report_id}")
async def get_report(request: Request, report_id: str, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    return _report_out(_owned_report(request, account, report_id))


class MoveIn(BaseModel):
    profile_id: str


@router.post("/reports/{report_id}/profile")
async def move_report(request: Request, report_id: str, body: MoveIn,
                      principal: Principal = Depends(current_principal)) -> dict:
    """Answer to "whose report is this?"."""
    account = load_account(request, principal)
    rec = _owned_report(request, account, report_id)
    _owned_profile(request, account, body.profile_id)
    rec.profile_id = body.profile_id
    rec.data["mismatch"] = []
    repo_of(request).save_report(rec)
    return _report_out(rec)


@router.delete("/reports/{report_id}")
async def delete_report(request: Request, report_id: str, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    if not repo_of(request).delete_report(account.id, report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    repo_of(request).audit(account.id, principal.role, "deleted_report")
    return {"deleted": True}


@router.get("/reports/{report_id}/messages")
async def report_messages(request: Request, report_id: str, principal: Principal = Depends(current_principal)) -> list[dict]:
    account = load_account(request, principal)
    _owned_report(request, account, report_id)
    out = []
    for rec in repo_of(request).exchanges(account.id, report_id):
        out += [{"role": "user", "content": rec.data["question"]}, {"role": "assistant", "content": rec.data["answer"]}]
    return out


# --- chat -----------------------------------------------------------------------------

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat_endpoint(request: Request, body: chat.ChatRequest,
                        principal: Principal = Depends(current_principal)) -> StreamingResponse:
    account = load_account(request, principal)
    need_consent(request, account)
    problem = chat.validate_request(body)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    repo = repo_of(request)
    report_text = None
    profile_id = body.profile_id
    if body.report_id:
        rec = _owned_report(request, account, body.report_id)
        if rec.data.get("status") != "ready":
            raise HTTPException(status_code=409, detail="This report is still being read.")
        report_text = chat.format_report(rec.data)
        profile_id = rec.profile_id
    profile = repo.profile(account.id, profile_id) if profile_id else None
    if metrics.over_budget():
        raise HTTPException(status_code=503, detail=BUDGET_MESSAGE)
    if not limits.take(account.id, "question", settings.daily_questions_per_user):
        raise HTTPException(status_code=429, detail="You've reached today's limit for questions. Please try again tomorrow.")
    metrics.event("chats")
    started = time.monotonic()

    async def events() -> AsyncIterator[str]:
        first = True
        async for event in chat.answer(body, report_text, request.app.state.kb,
                                       person_text(profile.data if profile else None)):
            if event["type"] == "text" and first:
                metrics.latency(time.monotonic() - started)
                first = False
            if event["type"] == "safety":
                metrics.event(f"safety_{event['verdict']}")
            if event["type"] == "error":
                metrics.event("errors")
            if event["type"] == "done":
                answer = event.pop("answer", None)
                if answer:
                    question = chat.redact_identifiers(body.messages[-1].content)
                    repo.save_exchange(account, profile_id, body.report_id, question, answer)
            yield _sse(event)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# --- trends ---------------------------------------------------------------------------

def _report_day(rec: Record) -> str:
    printed = parse_report_date(rec.data.get("report_date"))
    return printed.isoformat() if printed else rec.created_at[:10]


@router.get("/profiles/{profile_id}/trends")
async def trends(request: Request, profile_id: str, principal: Principal = Depends(current_principal)) -> dict:
    account = load_account(request, principal)
    _owned_profile(request, account, profile_id)
    recs = [r for r in repo_of(request).reports(account.id, profile_id) if r.data.get("status") == "ready"]
    timeline = sorted(
        ({"id": r.id, "date": _report_day(r), "report_type": r.data.get("report_type"),
          "flagged": sum(1 for x in r.data.get("rows", []) if x["status"] in ("low", "high", "abnormal", "critical")),
          "rows": r.data.get("rows", [])} for r in recs),
        key=lambda x: x["date"],
    )
    series = build_trends(timeline)
    changed = [s for s in series if s["change"] is not None and s["change"]["direction"] != "same"]
    return {
        "timeline": [{k: v for k, v in t.items() if k != "rows"} for t in reversed(timeline)],
        "series": series,
        "since_last_visit": changed,
        "history_enabled": bool(account.data.get("history_enabled")),
    }


# --- reminders --------------------------------------------------------------------------

class ScheduleIn(BaseModel):
    type: Literal["daily", "once", "monthly"] = "daily"
    time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    day: int | None = Field(default=None, ge=1, le=28)


class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["medicine", "test", "other"] = "medicine"
    profile_id: str | None = None
    schedule: ScheduleIn
    email: bool = True


@router.get("/reminders")
async def list_reminders(request: Request, principal: Principal = Depends(require_member)) -> list[dict]:
    account = load_account(request, principal)
    return [{"id": r.id, "profile_id": r.profile_id, **r.data} for r in repo_of(request).reminders(account.id)]


@router.post("/reminders")
async def add_reminder(request: Request, body: ReminderIn, principal: Principal = Depends(require_member)) -> dict:
    account = load_account(request, principal)
    need_consent(request, account)
    if body.profile_id:
        _owned_profile(request, account, body.profile_id)
    if body.schedule.type == "once" and not body.schedule.date:
        raise HTTPException(status_code=422, detail="Pick a date for a one-time reminder.")
    if len(repo_of(request).reminders(account.id)) >= 30:
        raise HTTPException(status_code=400, detail="That's the most reminders one account can have.")
    rec = repo_of(request).create_reminder(account, body.profile_id, {
        "title": body.title.strip(), "kind": body.kind, "schedule": body.schedule.model_dump(),
        "email": body.email and bool(account.data.get("email")),
        "active": True,
    })
    return {"id": rec.id, "profile_id": rec.profile_id, **rec.data}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(request: Request, reminder_id: str, principal: Principal = Depends(require_member)) -> dict:
    account = load_account(request, principal)
    if not repo_of(request).delete_reminder(account.id, reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"deleted": True}


# --- feedback ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)
    question: str | None = Field(default=None, max_length=4000)
    answer: str | None = Field(default=None, max_length=12000)
    language: str | None = None


@router.post("/feedback")
async def feedback(request: Request, body: FeedbackIn, principal: Principal = Depends(current_principal)) -> dict:
    load_account(request, principal)
    metrics.event(f"feedback_{body.rating}")
    if body.rating == "down" or body.comment:
        # Kept for the clinician review sample, redacted and not linked to the account.
        repo_of(request).add_feedback({
            "rating": body.rating,
            "comment": chat.redact_identifiers(body.comment or ""),
            "question": chat.redact_identifiers(body.question or ""),
            "answer": body.answer or "",
            "language": _lang(body.language),
        })
    return {"thanks": True}


# --- export -------------------------------------------------------------------------------

@router.get("/export.csv")
async def export_csv(request: Request, profile_id: str | None = None,
                     principal: Principal = Depends(current_principal)) -> Response:
    account = load_account(request, principal)
    repo = repo_of(request)
    profiles = {p.id: p for p in repo.profiles(account.id)}
    if profile_id and profile_id not in profiles:
        raise HTTPException(status_code=404, detail="Profile not found.")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["profile", "report_date", "report_type", "test", "value", "unit", "reference_range", "status"])
    for rec in sorted(repo.reports(account.id, profile_id), key=_report_day):
        if rec.data.get("status") != "ready":
            continue
        name = profiles.get(rec.profile_id).data.get("display_name") if rec.profile_id in profiles else ""
        for row in rec.data.get("rows", []):
            writer.writerow([name, _report_day(rec), rec.data.get("report_type") or "", row["test_name"], row["value"],
                             row.get("unit") or "", row.get("reference_range") or "", row["status"]])
    repo.audit(account.id, principal.role, "exported_csv")
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="carechat-results.csv"'})


# --- admin ----------------------------------------------------------------------------------

def _since(days: int) -> str:
    return iso(now() - timedelta(days=max(1, min(days, 400))))


@router.get("/admin/metrics")
async def admin_metrics(request: Request, days: int = 30, principal: Principal = Depends(require_admin)) -> dict:
    from .jobs import _tasks

    hours = repo_of(request).metrics_since(_since(days))
    return {**summarize(hours, metrics.snapshot(), days), "queue": {"reports_reading": len(_tasks)}}


@router.get("/admin/consents")
async def admin_consents(request: Request, days: int = 30, principal: Principal = Depends(require_admin)) -> dict:
    """Consent changes as counts per day and purpose. No names, no health values."""
    per_day: dict[str, Counter] = {}
    for rec in repo_of(request).consents_since(_since(days)):
        day = rec.created_at[:10]
        key = f"{rec.data['purpose']}_{'given' if rec.data['granted'] else 'withdrawn'}"
        per_day.setdefault(day, Counter())[key] += 1
    return {"days": [{"day": d, **dict(c)} for d, c in sorted(per_day.items())]}


@router.get("/admin/audit")
async def admin_audit(request: Request, days: int = 30, principal: Principal = Depends(require_admin)) -> list[dict]:
    events = [
        {"at": r.data.get("at"), "actor": (r.ref_id or "")[:8], "actor_role": r.data.get("actor_role"),
         "action": r.data.get("action"), "target": r.data.get("target")}
        for r in repo_of(request).audit_since(_since(days))
    ]
    return list(reversed(events))[:500]


@router.get("/admin/feedback")
async def admin_feedback(request: Request, days: int = 30, principal: Principal = Depends(require_admin)) -> list[dict]:
    repo = repo_of(request)
    repo.audit(principal.account_id, principal.role, "viewed_feedback_sample")
    return [{"id": r.id, **r.data} for r in reversed(repo.feedback_since(_since(days)))][:200]


class AdminDeleteIn(BaseModel):
    email: EmailStr


@router.post("/admin/delete-account")
async def admin_delete(request: Request, body: AdminDeleteIn, principal: Principal = Depends(require_admin)) -> dict:
    """For deletion requests that arrive by email (for example from a family member)."""
    repo = repo_of(request)
    account = repo.account_by_email(body.email)
    if account is None:
        raise HTTPException(status_code=404, detail="No account with that email.")
    n = repo.delete_account(account.id)
    repo.audit(principal.account_id, principal.role, "deleted_account_on_request", f"{account.id[:8]} ({n} records)")
    return {"deleted": True, "records": n}


# --- scheduled jobs ---------------------------------------------------------------------------

@router.post("/internal/hourly")
async def hourly(request: Request, x_cron_token: str | None = Header(default=None)) -> dict:
    if not settings.cron_token or not hmac.compare_digest(x_cron_token or "", settings.cron_token):
        raise HTTPException(status_code=403)
    return await run_hourly(repo_of(request))

