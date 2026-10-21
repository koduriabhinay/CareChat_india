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
