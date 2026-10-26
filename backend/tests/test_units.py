from datetime import datetime, timezone

import pytest

from carechat import auth
from carechat.results import bmi, is_critical, parse_range, parse_report_date, status_for
from carechat.scheduled import due_this_hour


@pytest.mark.parametrize("value, rng, flag, expected", [
    ("6.1", "4.0-5.6", "not_flagged", "high"),
    ("3.9", "4.0 - 5.6", "not_flagged", "low"),
    ("5.0", "4.0-5.6", "not_flagged", "normal"),
    ("250", "< 200", "not_flagged", "high"),
    ("45", "> 40", "not_flagged", "normal"),
    ("5.0", "4.0-5.6", "high", "high"),  # the report's own flag wins
    ("18", None, "not_flagged", "no_range"),
    ("Positive", "Negative", "not_flagged", "see_report"),
])
def test_status_for(value, rng, flag, expected):
    assert status_for(value, rng, flag) == expected


def test_parse_range_forms():
    assert parse_range("70 - 99") == (70, 99)
    assert parse_range("Up to 40") == (None, 40)


def test_critical_values_draft():
    assert is_critical("Potassium", "6.8", "mmol/L", "not_flagged")
    assert not is_critical("Potassium", "4.5", "mmol/L", "not_flagged")


def test_indian_date_formats_are_day_first():
    assert parse_report_date("03/04/2026").isoformat() == "2026-04-03"
    assert parse_report_date("12-Sep-2026").isoformat() == "2026-09-12"


def test_bmi_asian_cutoffs():
    assert bmi(170, 67)["band"] == "overweight"  # 23.2: normal by WHO, overweight by the Asian cut-offs
    assert bmi(170, 65)["band"] == "normal"
    assert bmi(None, 65) is None


def test_session_tokens_cannot_be_forged():
    token = auth.issue_token(auth.Principal("acc1", "patient", "a@b.c"))
    assert auth.read_token(token).account_id == "acc1"
    body, sig = token.split(".")
    import base64, json
    forged = base64.urlsafe_b64encode(json.dumps({"a": "acc1", "r": "admin", "x": 9999999999}).encode()).decode().rstrip("=")
    assert auth.read_token(f"{forged}.{sig}") is None
    assert auth.read_token(auth.issue_token(auth.Principal("acc1", "patient"), days=-1)) is None


def test_email_codes_expire_after_attempts():
    code = auth.new_email_code("x@y.com")
    for _ in range(5):
        auth.check_email_code("x@y.com", "000000" if code != "000000" else "111111")
    assert not auth.check_email_code("x@y.com", code)


def test_reminder_schedule_in_india_time():
    at = datetime(2026, 10, 21, 2, 45, tzinfo=timezone.utc)  # 08:15 IST
    assert due_this_hour({"type": "daily", "time": "08:00"}, at)
    assert not due_this_hour({"type": "daily", "time": "09:00"}, at)
    assert due_this_hour({"type": "once", "time": "08:30", "date": "2026-10-21"}, at)
    assert due_this_hour({"type": "monthly", "time": "08:00", "day": 21}, at)
    assert not due_this_hour({"type": "monthly", "time": "08:00", "day": 20}, at)


def test_normalize_indian_mobile_numbers():
    from carechat.sms import normalize_phone

    for raw in ("9876543210", "+91 98765 43210", "919876543210", "09876543210", "98765-43210"):
        assert normalize_phone(raw) == "+919876543210"
    for raw in ("", "5876543210", "98765", "+14155550100", "abcdefghij"):
        assert normalize_phone(raw) is None


def test_message_central_client(monkeypatch):
    """Send and check go to the documented VerifyNow endpoints, with a mocked network."""
    import asyncio

    import httpx

    from carechat import config, sms

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path == "/auth/v1/authentication/token":
            return httpx.Response(200, json={"status": 200, "token": "tok"})
        if path == "/verification/v3/send":
            if request.url.params["mobileNumber"] == "9000000000":
                return httpx.Response(400, json={"responseCode": 800, "message": "MAXIMUM_LIMIT_REACHED"})
            return httpx.Response(200, json={"responseCode": 200, "data": {"verificationId": "42", "timeout": "60"}})
        if path == "/verification/v3/validateOtp":
            ok = request.url.params["code"] == "123456"
            return httpx.Response(200 if ok else 400, json={
                "responseCode": 200 if ok else 702,
                "data": {"verificationStatus": "VERIFICATION_COMPLETED" if ok else "VERIFICATION_FAILED"},
            })
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(sms.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    saved = {}
    for name, value in {"sms_backend": "messagecentral", "mc_customer_id": "C-1", "mc_password": "pw"}.items():
        saved[name] = getattr(config.settings, name)
        object.__setattr__(config.settings, name, value)
    monkeypatch.setattr(sms, "_token", None)
    try:
        _run_message_central_checks(sms, calls)
    finally:
        for name, value in saved.items():
            object.__setattr__(config.settings, name, value)


def _run_message_central_checks(sms, calls):
    import asyncio


    assert sms.enabled()
    assert asyncio.run(sms.send_code("+919876543210")) is None
    token_req = calls[0]
    assert token_req.url.params["key"] == "cHc="  # base64 of "pw"
    send_req = calls[1]
    assert send_req.method == "POST" and send_req.headers["authToken"] == "tok"
    assert send_req.url.params["mobileNumber"] == "9876543210"

    assert asyncio.run(sms.check_code("+919876543210", "000000")) is False
    assert asyncio.run(sms.check_code("+919876543210", "123456")) is True
    assert calls[-1].url.params["verificationId"] == "42"
    # The verification is used up once it succeeds.
    assert asyncio.run(sms.check_code("+919876543210", "123456")) is False

    try:
        asyncio.run(sms.send_code("+919000000000"))
        raise AssertionError("expected SmsError")
    except sms.SmsError as exc:
        assert "Too many codes" in str(exc)


def test_dotenv_loader(tmp_path, monkeypatch):
    """backend/.env is read without `source`, including values with spaces and <>."""
    from carechat.config import _load_dotenv

    env = tmp_path / ".env"
    env.write_text('# comment\nCC_T_FROM=CareChat <no-reply@example.com>\nCC_T_KEY="abc"\nexport CC_T_X=1\nCC_T_SET=file\n')
    for k in ("CC_T_FROM", "CC_T_KEY", "CC_T_X"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CC_T_SET", "shell")
    _load_dotenv(env)
    import os

    assert os.environ["CC_T_FROM"] == "CareChat <no-reply@example.com>"
    assert os.environ["CC_T_KEY"] == "abc"
    assert os.environ["CC_T_X"] == "1"
    assert os.environ["CC_T_SET"] == "shell"  # the shell wins over the file
    for k in ("CC_T_FROM", "CC_T_KEY", "CC_T_X"):
        os.environ.pop(k, None)
