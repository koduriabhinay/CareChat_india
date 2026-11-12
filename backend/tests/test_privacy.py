from datetime import timedelta

import pytest

from carechat import store as store_module
from carechat.redact import REDACTED, redact, redact_identifiers
from carechat.reports import Report
from carechat.store import ReportStore


@pytest.mark.parametrize(
    "line, secret",
    [
        ("Name: Mr. Ravi Kumar   Age/Sex: 45/M", "Ravi"),
        ("Patient Name : Sunita Devi", "Sunita"),
        ("UHID: AB1234567", "AB1234567"),
        ("Ref. By: Dr. Priya Shah", "Priya"),
        ("Mobile: +91 98765 43210", "98765"),
        ("ravi.k@gmail.com", "ravi.k"),
        ("Aadhaar 1234 5678 9012", "5678"),
        ("ABHA: 12-3456-7890-1234", "3456"),
        ("DOB: 01/02/1980", "1980"),
        ("Collected for Smt. Lakshmi Iyer", "Lakshmi"),
    ],
)
def test_identifiers_are_redacted(line, secret):
    out = redact(line)
    assert secret not in out and REDACTED in out


@pytest.mark.parametrize(
    "line",
    [
        "Glucose, fasting     112      mg/dL     70-99             H",
        "Platelet count 150000 /cumm 150000-410000",
        "Test Name: Hemoglobin",
        "Age/Sex: 45/M",
    ],
)
def test_lab_values_are_kept(line):
    assert redact(line) == line


def test_chat_redaction_keeps_ordinary_text():
    assert redact_identifiers("My TSH is 4.5 and my name is Ravi") == "My TSH is 4.5 and my name is Ravi"
    assert "98765" not in redact_identifiers("my number is 9876543210")


def test_reports_expire(tmp_path, monkeypatch):
    s = ReportStore(str(tmp_path / "r.db"), retention_hours=24)
    report_id = s.save(Report(is_medical_report=True))
    assert s.get(report_id) is not None

    real_now = store_module._now
    monkeypatch.setattr(store_module, "_now", lambda: real_now() + timedelta(hours=25))
    assert s.get(report_id) is None
    assert s.purge_expired() == 1
