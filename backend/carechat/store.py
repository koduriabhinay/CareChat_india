"""Storage for uploaded reports.

Development uses a local SQLite file. Production should use an encrypted
database (for example Amazon RDS with encryption at rest) under a BAA.
Only the extracted results are stored; the original PDF is not kept.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .reports import Report


class ReportStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL)"
            )
            self._conn.commit()

    def save(self, report: Report) -> str:
        report_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO reports (id, created_at, data) VALUES (?, ?, ?)",
                (report_id, datetime.now(timezone.utc).isoformat(), report.model_dump_json()),
            )
            self._conn.commit()
        return report_id

    def get(self, report_id: str) -> Report | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM reports WHERE id = ?", (report_id,)).fetchone()
        return Report.model_validate_json(row[0]) if row else None

    def delete(self, report_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            self._conn.commit()
        return cur.rowcount > 0
