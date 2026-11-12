"""Storage for uploaded reports.

Only the extracted, redacted results are stored; the original PDF is not
kept. Reports are deleted automatically once they are older than the
retention period (24 hours by default), and users can delete them sooner.

Development uses a local SQLite file. Production should use an encrypted
database in an India region (for example Amazon RDS in Mumbai).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

from .reports import Report


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReportStore:
    def __init__(self, db_path: str, retention_hours: float = 24) -> None:
        self._retention = timedelta(hours=retention_hours)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL)"
            )
            self._conn.commit()
        self.purge_expired()

    def _cutoff(self) -> str:
        return (_now() - self._retention).isoformat()

    def purge_expired(self) -> int:
        """Delete every report older than the retention period."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM reports WHERE created_at < ?", (self._cutoff(),))
            self._conn.commit()
        return cur.rowcount

    def save(self, report: Report) -> str:
        self.purge_expired()
        report_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO reports (id, created_at, data) VALUES (?, ?, ?)",
                (report_id, _now().isoformat(), report.model_dump_json()),
            )
            self._conn.commit()
        return report_id

    def get(self, report_id: str) -> Report | None:
        """Return the report, or None if it doesn't exist or has expired."""
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM reports WHERE id = ? AND created_at >= ?", (report_id, self._cutoff())
            ).fetchone()
        return Report.model_validate_json(row[0]) if row else None

    def delete(self, report_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            self._conn.commit()
        return cur.rowcount > 0
