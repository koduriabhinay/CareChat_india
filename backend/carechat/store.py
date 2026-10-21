"""Record storage.

Every record lives in one table with a few plain columns used for lookups
(collection, ids, timestamps) and one `data` column holding the record's
content as encrypted JSON. One table keeps the Catalyst setup to a single
table, and encrypting `data` keeps health details unreadable at rest.

Backends:
- SQLiteStore: local development and tests.
- CatalystStore: Zoho Catalyst Data Store in production (see catalyst_store.py).

CachedStore wraps either one with an in-memory cache, because Catalyst's free
tier allows only 10,000 reads a month. It assumes a single API instance.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id() -> str:
    return uuid.uuid4().hex


def expiry(hours: float) -> str:
    return iso(now() + timedelta(hours=hours))


@dataclass
class Record:
    collection: str
    data: dict[str, Any]
    id: str = field(default_factory=new_id)
    account_id: str | None = None
    profile_id: str | None = None
    ref_id: str | None = None
    created_at: str = field(default_factory=lambda: iso(now()))
    expires_at: str | None = None  # None = kept until deleted

    def copy(self) -> "Record":
        return replace(self, data=json.loads(json.dumps(self.data)))


LOOKUP_FIELDS = ("account_id", "profile_id", "ref_id")


class RecordStore(Protocol):
    def insert(self, rec: Record) -> Record: ...
    def update(self, rec: Record) -> Record: ...
    def get(self, collection: str, record_id: str) -> Record | None: ...
    def find(self, collection: str, **where: str) -> list[Record]: ...
    def find_since(self, collection: str, since: str) -> list[Record]: ...
    def delete(self, collection: str, record_id: str) -> bool: ...
    def delete_where(self, **where: str) -> int: ...
    def purge_expired(self) -> int: ...


class Cipher:
    """Encrypts record content with a Fernet key (AES with an integrity check)."""

    def __init__(self, key: str) -> None:
        if not key:
            log.warning("CARECHAT_ENCRYPTION_KEY is not set; using a temporary key. Data won't survive a restart.")
            key = Fernet.generate_key().decode()
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def seal(self, data: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(data, separators=(",", ":")).encode()).decode()

    def open(self, token: str) -> dict[str, Any]:
        try:
            return json.loads(self._fernet.decrypt(token.encode()))
        except InvalidToken:
            log.error("A record could not be decrypted; the encryption key may have changed.")
            return {}


def _check_where(where: dict[str, str]) -> None:
    for key in where:
        if key not in LOOKUP_FIELDS + ("collection",):
            raise ValueError(f"Can't look records up by {key}")


class SQLiteStore:
    def __init__(self, path: str, cipher: Cipher) -> None:
        self._cipher = cipher
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS records (
                    doc_id TEXT PRIMARY KEY, collection TEXT NOT NULL, account_id TEXT, profile_id TEXT,
                    ref_id TEXT, created_at TEXT NOT NULL, expires_at TEXT, data TEXT NOT NULL)"""
            )
            for col in ("collection", "account_id", "profile_id", "ref_id", "expires_at"):
                self._conn.execute(f"CREATE INDEX IF NOT EXISTS ix_records_{col} ON records ({col})")
            self._conn.commit()

    def _row(self, row: tuple) -> Record:
        doc_id, collection, account_id, profile_id, ref_id, created_at, expires_at, data = row
        return Record(
            id=doc_id, collection=collection, account_id=account_id, profile_id=profile_id, ref_id=ref_id,
            created_at=created_at, expires_at=expires_at, data=self._cipher.open(data),
        )

    def _live(self) -> tuple[str, str]:
        return "(expires_at IS NULL OR expires_at > ?)", iso(now())

    def insert(self, rec: Record) -> Record:
        with self._lock:
            self._conn.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rec.id, rec.collection, rec.account_id, rec.profile_id, rec.ref_id, rec.created_at,
                 rec.expires_at, self._cipher.seal(rec.data)),
            )
            self._conn.commit()
        return rec

    def update(self, rec: Record) -> Record:
        with self._lock:
            self._conn.execute(
                "UPDATE records SET account_id=?, profile_id=?, ref_id=?, expires_at=?, data=? WHERE doc_id=?",
                (rec.account_id, rec.profile_id, rec.ref_id, rec.expires_at, self._cipher.seal(rec.data), rec.id),
            )
            self._conn.commit()
        return rec

    def get(self, collection: str, record_id: str) -> Record | None:
        live, ts = self._live()
        with self._lock:
            row = self._conn.execute(
                f"SELECT * FROM records WHERE doc_id=? AND collection=? AND {live}", (record_id, collection, ts)
            ).fetchone()
        return self._row(row) if row else None

    def find(self, collection: str, **where: str) -> list[Record]:
        _check_where(where)
        live, ts = self._live()
        clauses = ["collection=?", live] + [f"{k}=?" for k in where]
        params = [collection, ts, *where.values()]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM records WHERE {' AND '.join(clauses)} ORDER BY created_at", params
            ).fetchall()
        return [self._row(r) for r in rows]

    def find_since(self, collection: str, since: str) -> list[Record]:
        live, ts = self._live()
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM records WHERE collection=? AND created_at>=? AND {live} ORDER BY created_at",
                (collection, since, ts),
            ).fetchall()
        return [self._row(r) for r in rows]

    def delete(self, collection: str, record_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM records WHERE doc_id=? AND collection=?", (record_id, collection))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_where(self, **where: str) -> int:
        _check_where(where)
        if not where:
            raise ValueError("Refusing to delete every record")
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM records WHERE {' AND '.join(f'{k}=?' for k in where)}", tuple(where.values())
            )
            self._conn.commit()
        return cur.rowcount

    def purge_expired(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM records WHERE expires_at IS NOT NULL AND expires_at <= ?", (iso(now()),)
            )
            self._conn.commit()
        return cur.rowcount


class CachedStore:
    """Read-through cache in front of a store, so repeat reads (polling, chat turns) are free."""

    def __init__(self, inner: RecordStore, max_items: int = 5000) -> None:
        self.inner = inner
        self._items: dict[tuple[str, str], Record] = {}
        self._finds: dict[tuple, list[str]] = {}
        self._max = max_items
        self._lock = threading.RLock()

    def _alive(self, rec: Record) -> bool:
        return rec.expires_at is None or rec.expires_at > iso(now())

    def _remember(self, rec: Record) -> None:
        if len(self._items) >= self._max:
            self._items.clear()
            self._finds.clear()
        self._items[(rec.collection, rec.id)] = rec.copy()

    def _forget_finds(self, collection: str) -> None:
        for key in [k for k in self._finds if k[0] == collection]:
            del self._finds[key]

    def insert(self, rec: Record) -> Record:
        self.inner.insert(rec)
        with self._lock:
            self._remember(rec)
            self._forget_finds(rec.collection)
        return rec

    def update(self, rec: Record) -> Record:
        self.inner.update(rec)
        with self._lock:
            self._remember(rec)
            self._forget_finds(rec.collection)
        return rec

    def get(self, collection: str, record_id: str) -> Record | None:
        with self._lock:
            cached = self._items.get((collection, record_id))
        if cached is not None:
            return cached.copy() if self._alive(cached) else None
        rec = self.inner.get(collection, record_id)
        if rec is not None:
            with self._lock:
                self._remember(rec)
        return rec

    def find(self, collection: str, **where: str) -> list[Record]:
        key = (collection, tuple(sorted(where.items())))
        with self._lock:
            ids = self._finds.get(key)
            if ids is not None and all((collection, i) in self._items for i in ids):
                recs = [self._items[(collection, i)] for i in ids]
                return [r.copy() for r in recs if self._alive(r)]
        recs = self.inner.find(collection, **where)
        with self._lock:
            for r in recs:
                self._remember(r)
            self._finds[key] = [r.id for r in recs]
        return [r.copy() for r in recs]

    def find_since(self, collection: str, since: str) -> list[Record]:
        return self.inner.find_since(collection, since)

    def delete(self, collection: str, record_id: str) -> bool:
        with self._lock:
            self._items.pop((collection, record_id), None)
            self._forget_finds(collection)
        return self.inner.delete(collection, record_id)

    def delete_where(self, **where: str) -> int:
        with self._lock:
            self._items.clear()
            self._finds.clear()
        return self.inner.delete_where(**where)

    def purge_expired(self) -> int:
        with self._lock:
            for key in [k for k, r in self._items.items() if not self._alive(r)]:
                del self._items[key]
            self._finds.clear()
        return self.inner.purge_expired()


def build_store(settings) -> CachedStore:
    cipher = Cipher(settings.encryption_key)
    if settings.store_backend == "catalyst":
        from .catalyst_store import CatalystStore

        inner: RecordStore = CatalystStore(settings.catalyst_table, cipher)
    else:
        inner = SQLiteStore(settings.db_path, cipher)
    return CachedStore(inner)
