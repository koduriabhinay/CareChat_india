import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from carechat.reports import LabResult, Report
from carechat.summary import FlaggedNote, Summary


@pytest.fixture
def api(fake_client, db_path):
    from carechat.main import app

    with TestClient(app) as client:
        client.app.state.kb.add_document(
            "Hemoglobin A1C Test", "https://medlineplus.gov/a1c", "An A1C test measures average blood sugar."
        )
        yield client


def events(response):
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


def sign_in(api, email="ravi@example.com") -> dict:
    token = api.post("/api/auth/dev", json={"email": email}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def consent(api, h, history=False):
    r = api.post("/api/consents", headers=h, json={"processing": True, "terms": True, "adult": True, "history": history})
    assert r.status_code == 200, r.text
    return r.json()


def member(api, email="ravi@example.com", history=False, **profile) -> tuple[dict, str]:
    """A signed-in adult with consent given and their own profile."""
    h = sign_in(api, email)
    consent(api, h, history)
    body = {"display_name": "Ravi", "relation": "self", "name_on_reports": "Test Patient", "birth_year": 1980,
            "sex": "male", **profile}
    r = api.post("/api/profiles", headers=h, json=body)
    assert r.status_code == 200, r.text
    return h, r.json()["id"]


SAMPLE = Report(
    is_medical_report=True,
    report_type="Hemoglobin A1C",
    report_date="12/09/2026",
    patient_age="46 Y",
    patient_sex="male",
    results=[LabResult(test_name="HbA1c", value="6.1", unit="%", reference_range="4.0-5.6", flag="high"),
             LabResult(test_name="Hemoglobin", value="14.2", unit="g/dL", reference_range="13-17", flag="not_flagged")],
)
SUMMARY = Summary(
    overall="Most values are in range.",
    flagged=[FlaggedNote(test_name="HbA1c", meaning="A little above range [1].")],
    doctor_questions=["Should I repeat this test?", "What does this mean for me?"],
)


def sample_pdf() -> bytes:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples"))
    from make_sample_report import build

    return build()


def upload(api, h, profile_id, data=None, name="lab.pdf", media="application/pdf") -> dict:
    r = api.post("/api/reports", headers=h, data={"profile_id": profile_id},
                 files={"file": (name, data if data is not None else sample_pdf(), media)})
    assert r.status_code == 200, r.text
    return r.json()


def wait_ready(api, h, report_id) -> dict:
    for _ in range(100):
        body = api.get(f"/api/reports/{report_id}", headers=h).json()
        if body["status"] != "reading":
            return body
        time.sleep(0.02)
    raise AssertionError("report never finished reading")


# --- basics -------------------------------------------------------------------------------

def test_health(api):
    body = api.get("/api/health").json()
    assert body["knowledge_passages"] == 1
    assert body["region"] == "IN" and "112" in body["disclaimer"]
    assert body["dev_auth"] is True


def test_health_disclaimer_in_hindi(api):
    assert api.get("/api/health?language=hi").json()["disclaimer"] != api.get("/api/health").json()["disclaimer"]


def test_language_list_has_english_and_10_indian_languages(api):
    langs = api.get("/api/languages").json()
    assert [l["code"] for l in langs] == ["en", "hi", "bn", "te", "mr", "ta", "ur", "gu", "kn", "or", "ml"]


def test_requests_without_sign_in_are_rejected(api):
    assert api.get("/api/me").status_code == 401
    assert api.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401
    assert api.get("/api/me", headers={"Authorization": "Bearer forged.token"}).status_code == 401


# --- sign-in and consent -----------------------------------------------------------------------

def test_email_code_sign_in(api):
    r = api.post("/api/auth/email/start", json={"email": "Asha@Example.com"})
    code = r.json()["dev_code"]
    assert api.post("/api/auth/email/verify", json={"email": "asha@example.com", "code": "000000"}).status_code == 400
    r = api.post("/api/auth/email/verify", json={"email": "asha@example.com", "code": code})
    me = api.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["email"] == "asha@example.com" and me["role"] == "patient" and me["needs_consent"]


def test_bad_email_rejected(api):
    assert api.post("/api/auth/email/start", json={"email": "not-an-email"}).status_code == 422


def test_admin_role_comes_from_settings(api):
    assert api.get("/api/me", headers=sign_in(api, "admin@example.com")).json()["role"] == "admin"


def test_consent_is_needed_before_profiles_and_chat(api):
    h = sign_in(api)
    assert api.post("/api/profiles", headers=h, json={"display_name": "Me"}).status_code == 403
    assert api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 403


def test_under_18_is_blocked(api):
    h = sign_in(api)
    r = api.post("/api/consents", headers=h, json={"processing": True, "terms": True, "adult": False})
    assert r.status_code == 403
    consent(api, h)
    r = api.post("/api/profiles", headers=h, json={"display_name": "Me", "birth_year": 2015})
    assert r.status_code == 403


def test_guest_can_try_then_keep_profile_after_sign_in(api):
    guest = api.post("/api/auth/guest", json={}).json()["token"]
    gh = {"Authorization": f"Bearer {guest}"}
    consent(api, gh)
    pid = api.post("/api/profiles", headers=gh, json={"display_name": "Me"}).json()["id"]
    assert api.get("/api/reminders", headers=gh).status_code == 403  # members only
    token = api.post("/api/auth/dev", json={"email": "new@example.com", "guest_token": guest}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert [p["id"] for p in api.get("/api/profiles", headers=h).json()] == [pid]


# --- profiles -----------------------------------------------------------------------------------

def test_profile_form_and_bmi_with_asian_cutoffs(api):
    h, pid = member(api, height_cm=170, weight_kg=70, diet_type="jain", conditions=["Thyroid"])
    p = api.get(f"/api/profiles/{pid}", headers=h).json()
    assert p["bmi"]["value"] == 24.2 and p["bmi"]["band"] == "overweight"
    assert p["diet_type"] == "jain" and p["conditions"] == ["Thyroid"] and p["health_form_due"] is False


def test_family_profile_needs_their_agreement(api):
    h, _ = member(api)
    r = api.post("/api/profiles", headers=h, json={"display_name": "Amma", "relation": "mother"})
    assert r.status_code == 400
    r = api.post("/api/profiles", headers=h, json={"display_name": "Amma", "relation": "mother", "family_consent": True})
    assert r.status_code == 200
    assert len(api.get("/api/profiles", headers=h).json()) == 2


def test_other_accounts_cannot_see_profiles_or_reports(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    rid = upload(api, h, pid)["id"]
    wait_ready(api, h, rid)
    other, _ = member(api, "someone@example.com")
    assert api.get(f"/api/profiles/{pid}", headers=other).status_code == 404
    assert api.get(f"/api/reports/{rid}", headers=other).status_code == 404
    assert api.delete(f"/api/reports/{rid}", headers=other).status_code == 404
    assert api.post("/api/reports", headers=other, data={"profile_id": pid},
                    files={"file": ("a.pdf", sample_pdf(), "application/pdf")}).status_code == 404
    r = api.post("/api/chat", headers=other, json={"messages": [{"role": "user", "content": "hi"}], "report_id": rid})
    assert r.status_code == 404


# --- reports ------------------------------------------------------------------------------------

def test_report_is_read_with_status_summary_and_redaction(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    first = upload(api, h, pid)
    assert first["status"] == "reading"
    body = wait_ready(api, h, first["id"])
    assert body["status"] == "ready"
    rows = {r["test_name"]: r for r in body["rows"]}
    assert rows["HbA1c"]["status"] == "high" and rows["Hemoglobin"]["status"] == "normal"
    assert rows["HbA1c"]["reference_range"] == "4.0-5.6"
    assert body["summary"]["overall"] == "Most values are in range." and body["critical_message"] is None
    assert body["sources"][0]["url"] == "https://medlineplus.gov/a1c"
    assert body["mismatch"] == [] and body["suggested_profile_id"] == pid

    sent = next(k for name, k in fake_client.calls if name == "report")["messages"][0]["content"]
    assert isinstance(sent, str) and "Hemoglobin A1c" in sent
    assert "Test Patient" not in sent and "[REDACTED]" in sent
    summary_call = next(k for name, k in fake_client.calls if name == "summary")
    assert "HbA1c | 6.1 | % | 4.0-5.6 | high" in summary_call["messages"][0]["content"]


def test_photo_is_sent_as_an_image(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    body = wait_ready(api, h, upload(api, h, pid, png, "photo.png", "image/png")["id"])
    assert body["status"] == "ready" and body["source"] == "image"
    content = next(k for name, k in fake_client.calls if name == "report")["messages"][0]["content"]
    assert any(block["type"] == "image" for block in content)


def test_critical_value_shows_fixed_message_first(api, fake_client):
    fake_client.report = Report(is_medical_report=True, results=[
        LabResult(test_name="Potassium", value="7.2", unit="mmol/L", reference_range="3.5-5.1", flag="high")])
    fake_client.summary = SUMMARY
    h, pid = member(api)
    body = wait_ready(api, h, upload(api, h, pid)["id"])
    assert body["critical"] and "112" in body["critical_message"]


def test_missing_range_is_marked(api, fake_client):
    fake_client.report = Report(is_medical_report=True, results=[
        LabResult(test_name="Vitamin D", value="18", unit="ng/mL", reference_range=None, flag="not_flagged")])
    fake_client.summary = SUMMARY
    h, pid = member(api)
    body = wait_ready(api, h, upload(api, h, pid)["id"])
    assert body["rows"][0]["status"] == "no_range"


def test_mismatch_when_report_age_differs(api, fake_client):
    fake_client.report = SAMPLE.model_copy(update={"patient_age": "70 Y"})
    fake_client.summary = SUMMARY
    h, pid = member(api)
    body = wait_ready(api, h, upload(api, h, pid)["id"])
    assert body["mismatch"] == ["age"]


def test_summary_failure_still_shows_table(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, None
    h, pid = member(api)
    body = wait_ready(api, h, upload(api, h, pid)["id"])
    assert body["status"] == "ready" and body["summary"] is None and len(body["rows"]) == 2


def test_upload_rejects_other_files(api):
    h, pid = member(api)
    r = api.post("/api/reports", headers=h, data={"profile_id": pid}, files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and "PDF" in r.json()["detail"]


def test_non_medical_document_fails(api, fake_client):
    fake_client.report = Report(is_medical_report=False)
    h, pid = member(api)
    body = wait_ready(api, h, upload(api, h, pid)["id"])
    assert body["status"] == "failed" and body["error_code"] == "not_medical"


def test_scanned_pdf_asks_for_photo_without_calling_claude(api, fake_client):
    h, pid = member(api)
    body = wait_ready(api, h, upload(api, h, pid, b"%PDF-1.4 no text layer")["id"])
    assert body["status"] == "failed" and body["error_code"] == "scanned_pdf" and "photo" in body["error"]
    assert not [c for c in fake_client.calls if c[0] == "report"]


def test_daily_report_limit(api, fake_client):
    from carechat import config

    object.__setattr__(config.settings, "daily_reports_per_user", 1)
    try:
        fake_client.report, fake_client.summary = SAMPLE, SUMMARY
        h, pid = member(api)
        upload(api, h, pid)
        r = api.post("/api/reports", headers=h, data={"profile_id": pid},
                     files={"file": ("a.pdf", sample_pdf(), "application/pdf")})
        assert r.status_code == 429
    finally:
        object.__setattr__(config.settings, "daily_reports_per_user", 10)


def test_move_report_to_family_member(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    amma = api.post("/api/profiles", headers=h, json={"display_name": "Amma", "relation": "mother",
                                                       "family_consent": True}).json()["id"]
    rid = upload(api, h, pid)["id"]
    wait_ready(api, h, rid)
    assert api.post(f"/api/reports/{rid}/profile", headers=h, json={"profile_id": amma}).json()["profile_id"] == amma


# --- chat ---------------------------------------------------------------------------------------

def test_self_harm_points_to_tele_manas(api):
    h, _ = member(api)
    ev = events(api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "I want to end my life"}]}))
    assert ev[0]["verdict"] == "self_harm" and ev[0]["call"] == "14416"
    assert "Tele-MANAS" in ev[0]["message"]


def test_chat_streams_answer_with_sources(api, fake_client):
    h, _ = member(api)
    ev = events(api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "What is A1C?"}]}))
    assert ev[0]["type"] == "sources" and ev[0]["sources"][0]["url"] == "https://medlineplus.gov/a1c"
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Hello there."
    assert ev[-1] == {"type": "done"}  # the full answer is not sent twice
    sent = fake_client.calls[-1][1]
    assert "<sources>" in sent["messages"][-1]["content"]
    assert sent["fallbacks"] == "default"


def test_emergency_never_reaches_answer_model(api, fake_client):
    h, _ = member(api)
    ev = events(api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "I have crushing chest pain"}]}))
    assert ev[0]["type"] == "safety" and ev[0]["verdict"] == "emergency"
    assert "112" in ev[0]["message"] and ev[0]["call"] == "112"
    assert all(kind != "answer" for kind, _ in fake_client.calls)


def test_safety_message_in_each_language_keeps_numbers(api):
    h, _ = member(api)
    for lang in ("hi", "ta", "bn", "ur"):
        ev = events(api.post("/api/chat", headers=h, json={
            "messages": [{"role": "user", "content": "I want to end my life"}], "language": lang}))
        assert "14416" in ev[0]["message"]


def test_safety_message_in_hindi(api):
    h, _ = member(api)
    ev = events(api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "सीने में दर्द हो रहा है"}], "language": "hi"}))
    assert ev[0]["verdict"] == "emergency" and "112" in ev[0]["message"] and "कृपया" in ev[0]["message"]


def test_refusal_replaces_partial_text(api, fake_client):
    h, _ = member(api)
    fake_client.answer_stop = "refusal"
    ev = events(api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "hi"}]}))
    assert any(e["type"] == "replace" for e in ev)


def test_rejects_conversation_ending_with_assistant(api):
    h, _ = member(api)
    r = api.post("/api/chat", headers=h,
                 json={"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]})
    assert r.status_code == 422


def test_chat_about_report_uses_cached_report_and_person(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api, history=True, diet_type="vegetarian", medicines=["Metformin"])
    rid = upload(api, h, pid)["id"]
    wait_ready(api, h, rid)
    api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "Explain my results"}], "report_id": rid})
    system = fake_client.calls[-1][1]["system"]
    assert "HbA1c | 6.1 | % | 4.0-5.6 | high" in system[1]["text"]
    assert "vegetarian" in system[1]["text"] and system[1]["cache_control"] == {"type": "ephemeral"}
    # With history on, the exchange is saved.
    assert api.get(f"/api/reports/{rid}/messages", headers=h).json()[1]["content"] == "Hello there."

    assert api.delete(f"/api/reports/{rid}", headers=h).json() == {"deleted": True}
    r = api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "x"}], "report_id": rid})
    assert r.status_code == 404


def test_chat_strips_phone_numbers(api, fake_client):
    h, _ = member(api)
    api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "call me on 98765 43210 about my A1C"}]})
    for _, kwargs in fake_client.calls:
        assert "98765" not in json.dumps(kwargs["messages"])


def test_reply_language_is_sent_to_model(api, fake_client):
    h, _ = member(api)
    api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "What is A1C?"}], "language": "ta"})
    assert "<reply_language>Tamil</reply_language>" in fake_client.calls[-1][1]["messages"][-1]["content"]


def test_unknown_language_rejected(api):
    h, _ = member(api)
    r = api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "hi"}], "language": "xx"})
    assert r.status_code == 422


def test_monthly_budget_stops_new_work(api, fake_client):
    from carechat.metrics import metrics

    h, pid = member(api)
    metrics.cost = 10_000
    r = api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503
    r = api.post("/api/reports", headers=h, data={"profile_id": pid}, files={"file": ("a.pdf", sample_pdf(), "application/pdf")})
    assert r.status_code == 503


# --- history, trends, delete -----------------------------------------------------------------------

def test_trends_compare_with_last_visit(api, fake_client):
    h, pid = member(api, history=True)
    fake_client.summary = SUMMARY
    for date, value in (("01/03/2026", "5.6"), ("01/09/2026", "7.5")):
        fake_client.report = Report(is_medical_report=True, report_date=date, results=[
            LabResult(test_name="HbA1c", value=value, unit="%", reference_range="4.0-5.6", flag="not_flagged")])
        wait_ready(api, h, upload(api, h, pid)["id"])
    t = api.get(f"/api/profiles/{pid}/trends", headers=h).json()
    a1c = next(s for s in t["series"] if s["key"] == t["since_last_visit"][0]["key"])
    assert [p["value"] for p in a1c["points"]] == [5.6, 7.5]
    assert a1c["change"]["direction"] == "up" and a1c["change"]["big"] is True
    assert t["timeline"][0]["date"] == "2026-09-01"


def test_without_history_reports_expire_and_chat_is_not_saved(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    rid = upload(api, h, pid)["id"]
    body = wait_ready(api, h, rid)
    assert body["expires_at"] is not None
    api.post("/api/chat", headers=h, json={"messages": [{"role": "user", "content": "Explain"}], "report_id": rid})
    assert api.get(f"/api/reports/{rid}/messages", headers=h).json() == []


def test_turning_history_on_keeps_reports_and_off_deletes_them(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    rid = upload(api, h, pid)["id"]
    wait_ready(api, h, rid)
    api.post("/api/me/history", headers=h, json={"enabled": True})
    assert api.get(f"/api/reports/{rid}", headers=h).json()["expires_at"] is None
    api.post("/api/me/history", headers=h, json={"enabled": False})
    assert api.get(f"/api/reports/{rid}", headers=h).status_code == 404


def test_delete_account_removes_everything(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api, history=True)
    wait_ready(api, h, upload(api, h, pid)["id"])
    assert api.delete("/api/me", headers=h).json() == {"deleted": True}
    assert api.get("/api/me", headers=h).status_code == 401
    h2 = sign_in(api)  # same email, fresh start
    assert api.get("/api/profiles", headers=h2).json() == []


def test_csv_export(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    wait_ready(api, h, upload(api, h, pid)["id"])
    text = api.get("/api/export.csv", headers=h).text
    assert "HbA1c,6.1,%,4.0-5.6,high" in text


# --- reminders, feedback ------------------------------------------------------------------------

def test_reminders(api):
    h, pid = member(api)
    r = api.post("/api/reminders", headers=h, json={"title": "Thyroid tablet", "profile_id": pid,
                                                    "schedule": {"type": "daily", "time": "08:00"}})
    assert r.status_code == 200
    assert len(api.get("/api/reminders", headers=h).json()) == 1
    bad = api.post("/api/reminders", headers=h, json={"title": "x", "schedule": {"type": "once", "time": "08:00"}})
    assert bad.status_code == 422
    assert api.delete(f"/api/reminders/{r.json()['id']}", headers=h).json() == {"deleted": True}


def test_feedback_is_stored_redacted_and_unlinked(api):
    h, _ = member(api)
    api.post("/api/feedback", headers=h, json={"rating": "down", "comment": "wrong, call 9876543210",
                                               "question": "q", "answer": "a"})
    admin = sign_in(api, "admin@example.com")
    items = api.get("/api/admin/feedback", headers=admin).json()
    assert len(items) == 1 and "9876543210" not in items[0]["comment"]
    assert "account_id" not in items[0] and "email" not in items[0]


# --- admin and jobs -------------------------------------------------------------------------------

def test_admin_pages_need_admin(api):
    h, _ = member(api)
    for path in ("/api/admin/metrics", "/api/admin/consents", "/api/admin/audit", "/api/admin/feedback"):
        assert api.get(path, headers=h).status_code == 403


def test_admin_metrics_have_no_names_or_values(api, fake_client):
    fake_client.report, fake_client.summary = SAMPLE, SUMMARY
    h, pid = member(api)
    wait_ready(api, h, upload(api, h, pid)["id"])
    admin = sign_in(api, "admin@example.com")
    m = api.get("/api/admin/metrics", headers=admin).json()
    text = json.dumps(m)
    assert "ravi" not in text.lower() and "6.1" not in text and "HbA1c" not in text
    assert m["days"][-1]["events"]["reports_uploaded"] == 1
    consents = api.get("/api/admin/consents", headers=admin).json()
    assert consents["days"][0]["processing_given"] >= 1


def test_hourly_job_needs_token(api):
    assert api.post("/api/internal/hourly").status_code == 403
    r = api.post("/api/internal/hourly", headers={"X-Cron-Token": "cron-secret"})
    assert r.status_code == 200 and "purged" in r.json()


# --- mobile number sign-in ------------------------------------------------------------

def phone_sign_in(api, phone="98765 43210", guest_token=None):
    start = api.post("/api/auth/phone/start", json={"phone": phone})
    assert start.status_code == 200, start.text
    r = api.post("/api/auth/phone/verify", json={"phone": phone, "code": start.json()["dev_code"], "guest_token": guest_token})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_phone_sign_in(api):
    assert api.get("/api/health").json()["phone_sign_in"] is True
    h = phone_sign_in(api, "+91 98765 43210")
    me = api.get("/api/me", headers=h).json()
    assert me["phone"] == "+919876543210" and me["email"] is None and me["role"] == "patient"
    # The same number in another format reaches the same account.
    assert api.get("/api/me", headers=phone_sign_in(api, "09876543210")).json()["id"] == me["id"]


def test_phone_rejects_bad_numbers_and_codes(api):
    for bad in ("12345", "5876543210", "+1 415 555 0100"):
        assert api.post("/api/auth/phone/start", json={"phone": bad}).status_code == 422
    api.post("/api/auth/phone/start", json={"phone": "9876543210"})
    assert api.post("/api/auth/phone/verify", json={"phone": "9876543210", "code": "000000"}).status_code == 400


def test_phone_codes_are_limited_per_number_and_per_day(api):
    from carechat import config

    for _ in range(3):
        assert api.post("/api/auth/phone/start", json={"phone": "9876500001"}).status_code == 200
    assert api.post("/api/auth/phone/start", json={"phone": "9876500001"}).status_code == 429
    object.__setattr__(config.settings, "daily_sms_cap", 3)
    try:
        assert api.post("/api/auth/phone/start", json={"phone": "9876500002"}).status_code == 429
    finally:
        object.__setattr__(config.settings, "daily_sms_cap", 100)


def test_phone_sign_in_keeps_guest_data(api):
    guest = api.post("/api/auth/guest", json={}).json()["token"]
    gh = {"Authorization": f"Bearer {guest}"}
    consent(api, gh)
    pid = api.post("/api/profiles", headers=gh, json={"display_name": "Me"}).json()["id"]
    h = phone_sign_in(api, guest_token=guest)
    assert [p["id"] for p in api.get("/api/profiles", headers=h).json()] == [pid]


def test_phone_only_reminders_are_in_app(api):
    h = phone_sign_in(api)
    consent(api, h)
    r = api.post("/api/reminders", headers=h, json={"title": "Tablet", "schedule": {"type": "daily", "time": "08:00"}})
    assert r.json()["email"] is False


def test_phone_sign_in_off(api):
    from carechat import config

    object.__setattr__(config.settings, "sms_backend", "off")
    try:
        assert api.get("/api/health").json()["phone_sign_in"] is False
        assert api.post("/api/auth/phone/start", json={"phone": "9876543210"}).status_code == 404
    finally:
        object.__setattr__(config.settings, "sms_backend", "console")
