"""Zoho Catalyst Data Store backend.

Needs one Data Store table (default name `records`) with these columns, all
type Text or Var Char as noted (see README):

    doc_id      Var Char (64), unique
    collection  Var Char (32)
    account_id  Var Char (64)
    profile_id  Var Char (64)
    ref_id      Var Char (64)
    created_at  Var Char (32)
    expires_at  Var Char (32)
    data        Text

How the SDK gets credentials:
- Inside AppSail, Catalyst adds X-ZC-* headers to every request. The API
  remembers the latest ones (see main.py) and uses them here.
- Or set CATALYST_AUTH and CATALYST_OPTIONS (a refresh token; see the
  zcatalyst-sdk docs), which also works for background jobs.

This file can't be tested without a Catalyst project; the SQLite backend
shares the same behaviour and is what the automated tests use.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from types import SimpleNamespace
from typing import Any

from .store import Cipher, Record, _check_where, iso, now

log = logging.getLogger(__name__)

_SAFE = re.compile(r"^[A-Za-z0-9_.:\-]+$")
_PAGE = 300  # ZCQL returns at most 300 rows per query

_headers_lock = threading.Lock()
_latest_headers: dict[str, str] = {}


def remember_request_headers(headers: Any) -> None:
    """Keep the newest Catalyst credential headers for calls made outside a request."""
    zc = {k: v for k, v in dict(headers).items() if k.lower().startswith("x-zc-")}
    if zc:
        with _headers_lock:
            _latest_headers.clear()
            _latest_headers.update(zc)


def _quote(value: str) -> str:
    if not _SAFE.match(value):
        raise ValueError("Unsafe value in a Data Store query")
    return f"'{value}'"


class CatalystStore:
    COLUMNS = ("doc_id", "collection", "account_id", "profile_id", "ref_id", "created_at", "expires_at", "data")

    def __init__(self, table: str, cipher: Cipher) -> None:
        if not _SAFE.match(table):
            raise ValueError("Bad table name")
        self._table = table
        self._cipher = cipher

    # --- SDK access ---------------------------------------------------------
    def _app(self):
        import zcatalyst_sdk

        if os.getenv("CATALYST_AUTH"):
            try:
                return zcatalyst_sdk.get_app()
            except Exception:  # not initialised in this thread yet
                return zcatalyst_sdk.initialize_app()
        with _headers_lock:
            headers = dict(_latest_headers)
        if not headers:
            raise RuntimeError("No Catalyst credentials yet: no request has reached the API.")
        return zcatalyst_sdk.initialize(req=SimpleNamespace(headers=headers))

    def _query(self, sql: str) -> list[dict[str, Any]]:
        rows = self._app().zcql().execute_query(sql) or []
        return [r.get(self._table, r) for r in rows]

    def _select(self, where: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        start = 1
        while True:
            page = self._query(
                f"SELECT * FROM {self._table} WHERE {where} ORDER BY created_at LIMIT {start},{_PAGE}"
            )
            out.extend(page)
            if len(page) < _PAGE:
                return out
            start += _PAGE

    def _table_api(self):
        return self._app().datastore().table(self._table)

    # --- conversions --------------------------------------------------------
    def _row(self, row: dict[str, Any]) -> Record:
        return Record(
            id=row["doc_id"], collection=row["collection"], account_id=row.get("account_id") or None,
            profile_id=row.get("profile_id") or None, ref_id=row.get("ref_id") or None,
            created_at=row["created_at"], expires_at=row.get("expires_at") or None,
            data=self._cipher.open(row.get("data") or ""),
        )

    def _values(self, rec: Record) -> dict[str, Any]:
        return {
            "doc_id": rec.id, "collection": rec.collection, "account_id": rec.account_id or "",
            "profile_id": rec.profile_id or "", "ref_id": rec.ref_id or "", "created_at": rec.created_at,
            "expires_at": rec.expires_at or "", "data": self._cipher.seal(rec.data),
        }

    def _live(self) -> str:
        return f"(expires_at = '' OR expires_at IS NULL OR expires_at > {_quote(iso(now()))})"

    def _rowids(self, where: str) -> list[str]:
        return [str(r["ROWID"]) for r in self._select(where)]

    # --- RecordStore --------------------------------------------------------
    def insert(self, rec: Record) -> Record:
        self._table_api().insert_row(self._values(rec))
        return rec

    def update(self, rec: Record) -> Record:
        ids = self._rowids(f"doc_id = {_quote(rec.id)}")
        if not ids:
            raise KeyError(rec.id)
        self._table_api().update_row({"ROWID": ids[0], **self._values(rec)})
        return rec

    def get(self, collection: str, record_id: str) -> Record | None:
        rows = self._select(
            f"doc_id = {_quote(record_id)} AND collection = {_quote(collection)} AND {self._live()}"
        )
        return self._row(rows[0]) if rows else None

    def find(self, collection: str, **where: str) -> list[Record]:
        _check_where(where)
        clauses = [f"collection = {_quote(collection)}", self._live()]
        clauses += [f"{k} = {_quote(v)}" for k, v in where.items()]
        return [self._row(r) for r in self._select(" AND ".join(clauses))]

    def find_since(self, collection: str, since: str) -> list[Record]:
        rows = self._select(f"collection = {_quote(collection)} AND created_at >= {_quote(since)} AND {self._live()}")
        return [self._row(r) for r in rows]

    def _delete_ids(self, ids: list[str]) -> int:
        table = self._table_api()
        for i in range(0, len(ids), 100):
            table.delete_rows(ids[i : i + 100])
        return len(ids)

    def delete(self, collection: str, record_id: str) -> bool:
        ids = self._rowids(f"doc_id = {_quote(record_id)} AND collection = {_quote(collection)}")
        return self._delete_ids(ids) > 0

    def delete_where(self, **where: str) -> int:
        _check_where(where)
        if not where:
            raise ValueError("Refusing to delete every record")
        return self._delete_ids(self._rowids(" AND ".join(f"{k} = {_quote(v)}" for k, v in where.items())))

    def purge_expired(self) -> int:
        stamp = _quote(iso(now()))
        return self._delete_ids(self._rowids(f"expires_at != '' AND expires_at <= {stamp}"))
