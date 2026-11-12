"""CatalystStore against a fake Data Store that runs the ZCQL on SQLite."""

import re
import sqlite3
from datetime import timedelta
from types import SimpleNamespace

import pytest

from carechat import store as store_module
from carechat.catalyst_store import CatalystStore
from carechat.store import Cipher, Record, expiry

COLUMNS = CatalystStore.COLUMNS


class FakeDataStore:
    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.execute(f"CREATE TABLE records ({', '.join(c + ' TEXT' for c in COLUMNS)})")
        self.queries: list[str] = []

    # zcql().execute_query
    def execute_query(self, sql: str):
        self.queries.append(sql)
        m = re.search(r"LIMIT (\d+),(\d+)$", sql)
        assert m, "every select must be paged"
        sql = sql[: m.start()] + f"LIMIT {m.group(2)} OFFSET {int(m.group(1)) - 1}"
        sql = sql.replace("SELECT *", "SELECT rowid AS ROWID, *")
        cur = self.db.execute(sql)
        names = [d[0] for d in cur.description]
        return [{"records": dict(zip(names, row))} for row in cur.fetchall()]

    # datastore().table("records")
    def insert_row(self, values):
        self.db.execute(f"INSERT INTO records ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                        list(values.values()))

    def update_row(self, values):
        rowid = values.pop("ROWID")
        self.db.execute(f"UPDATE records SET {', '.join(k + '=?' for k in values)} WHERE rowid=?",
                        [*values.values(), rowid])

    def delete_rows(self, ids):
        assert len(ids) <= 100
        self.db.execute(f"DELETE FROM records WHERE rowid IN ({', '.join('?' * len(ids))})", ids)

    def app(self):
        return SimpleNamespace(zcql=lambda: self, datastore=lambda: SimpleNamespace(table=lambda name: self))


@pytest.fixture
def cat(monkeypatch):
    fake = FakeDataStore()
    s = CatalystStore("records", Cipher(""))
    monkeypatch.setattr(s, "_app", fake.app)
    return s, fake


def test_insert_get_find_update_delete(cat):
    s, fake = cat
    rec = s.insert(Record(collection="profile", account_id="acc1", data={"display_name": "Ravi"}))
    assert s.get("profile", rec.id).data == {"display_name": "Ravi"}
    assert "Ravi" not in str(fake.db.execute("SELECT data FROM records").fetchall())  # encrypted
    rec.data["display_name"] = "Ravi K"
    s.update(rec)
    assert [r.data["display_name"] for r in s.find("profile", account_id="acc1")] == ["Ravi K"]
    assert s.find("profile", account_id="other") == []
    assert s.delete("profile", rec.id) and s.get("profile", rec.id) is None


def test_paging_past_300_rows(cat):
    s, _ = cat
    for i in range(305):
        s.insert(Record(collection="audit", ref_id="a", data={"i": i}))
    assert len(s.find("audit", ref_id="a")) == 305
    assert s.delete_where(ref_id="a") == 305


def test_expiry(cat, monkeypatch):
    s, _ = cat
    rec = s.insert(Record(collection="report", account_id="a", data={}, expires_at=expiry(24)))
    keep = s.insert(Record(collection="report", account_id="a", data={}))
    real_now = store_module.now
    monkeypatch.setattr("carechat.catalyst_store.now", lambda: real_now() + timedelta(hours=25))
    assert s.get("report", rec.id) is None and s.get("report", keep.id) is not None
    assert s.purge_expired() == 1


def test_rejects_unsafe_values(cat):
    s, _ = cat
    with pytest.raises(ValueError):
        s.find("profile", account_id="x' OR '1'='1")
