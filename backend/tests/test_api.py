import json

import pytest
from fastapi.testclient import TestClient

from carechat.reports import LabResult, Report


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


SAMPLE = Report(
    is_medical_report=True,
    report_type="Hemoglobin A1C",
    results=[LabResult(test_name="HbA1c", value="6.1", unit="%", reference_range="4.0-5.6", flag="high")],
)


def test_health(api):
    body = api.get("/api/health").json()
    assert body["knowledge_passages"] == 1
    assert body["region"] == "IN" and "112" in body["disclaimer"]


def test_self_harm_points_to_tele_manas(api):
    ev = events(api.post("/api/chat", json={"messages": [{"role": "user", "content": "I want to end my life"}]}))
    assert ev[0]["verdict"] == "self_harm" and ev[0]["call"] == "14416"
    assert "Tele-MANAS" in ev[0]["message"]


def test_chat_streams_answer_with_sources(api, fake_client):
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "What is A1C?"}]})
    ev = events(r)
    assert ev[0]["type"] == "sources" and ev[0]["sources"][0]["url"] == "https://medlineplus.gov/a1c"
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Hello there."
    assert ev[-1]["type"] == "done"
    sent = fake_client.calls[-1][1]
    assert "<sources>" in sent["messages"][-1]["content"]
    assert sent["fallbacks"] == "default"


def test_emergency_never_reaches_answer_model(api, fake_client):
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "I have crushing chest pain"}]})
    ev = events(r)
    assert ev[0]["type"] == "safety" and ev[0]["verdict"] == "emergency"
    assert "112" in ev[0]["message"] and ev[0]["call"] == "112"
    assert all(kind != "answer" for kind, _ in fake_client.calls)


def test_refusal_replaces_partial_text(api, fake_client):
    fake_client.answer_stop = "refusal"
    ev = events(api.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}))
    assert any(e["type"] == "replace" for e in ev)


def test_rejects_conversation_ending_with_assistant(api):
    r = api.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]},
    )
    assert r.status_code == 422


def test_report_upload_then_chat_includes_report(api, fake_client):
    fake_client.report = SAMPLE
    r = api.post("/api/reports", files={"file": ("lab.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 200
    report_id = r.json()["report_id"]
    sent_doc = fake_client.calls[-1][1]["messages"][0]["content"][0]
    assert sent_doc["type"] == "document" and sent_doc["source"]["media_type"] == "application/pdf"

    api.post("/api/chat", json={"messages": [{"role": "user", "content": "Explain my results"}], "report_id": report_id})
    prompt = fake_client.calls[-1][1]["messages"][-1]["content"]
    assert "HbA1c | 6.1 | % | 4.0-5.6 | high" in prompt

    assert api.delete(f"/api/reports/{report_id}").json() == {"deleted": True}
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "x"}], "report_id": report_id})
    assert r.status_code == 404


def test_upload_rejects_non_pdf(api):
    r = api.post("/api/reports", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and "PDF" in r.json()["detail"]


def test_upload_rejects_non_medical_document(api, fake_client):
    fake_client.report = Report(is_medical_report=False)
    r = api.post("/api/reports", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 422
