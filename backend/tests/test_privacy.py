from datetime import timedelta

import pytest

from carechat import store as store_module
from carechat.redact import REDACTED, redact, redact_identifiers
from carechat.store import Cipher, Record, SQLiteStore, expiry


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


def test_records_expire(tmp_path, monkeypatch):
    s = SQLiteStore(str(tmp_path / "r.db"), Cipher(""))
    rec = s.insert(Record(collection="report", account_id="a", data={"x": 1}, expires_at=expiry(24)))
    assert s.get("report", rec.id) is not None

    real_now = store_module.now
    monkeypatch.setattr(store_module, "now", lambda: real_now() + timedelta(hours=25))
    assert s.get("report", rec.id) is None
    assert s.purge_expired() == 1


def test_health_data_is_encrypted_at_rest(tmp_path):
    import sqlite3

    path = str(tmp_path / "r.db")
    s = SQLiteStore(path, Cipher(""))
    s.insert(Record(collection="report", account_id="a", data={"rows": [{"test_name": "HbA1c", "value": "6.1"}]}))
    raw = sqlite3.connect(path).execute("SELECT data FROM records").fetchone()[0]
    assert "HbA1c" not in raw and "6.1" not in raw


def test_delete_where_refuses_empty_filter(tmp_path):
    s = SQLiteStore(str(tmp_path / "r.db"), Cipher(""))
    with pytest.raises(ValueError):
        s.delete_where()


def test_printed_name_and_known_names_are_redacted():
    from carechat.redact import printed_name, redact_names

    assert printed_name("Patient Name : Sunita Devi\nAge: 54") == "Sunita Devi"
    assert "Sunita" not in redact_names("Report for Sunita, Hb 12", ["Sunita Devi"])
