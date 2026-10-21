"""Per-user daily limits, kept in memory (the API runs as one instance)."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone


class DailyLimits:
    def __init__(self) -> None:
        self._day = ""
        self._counts: Counter[tuple[str, str]] = Counter()
        self._lock = threading.Lock()

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day = today
            self._counts.clear()

    def take(self, key: str, kind: str, limit: int) -> bool:
        """Count one use; False if the daily limit is already reached."""
        with self._lock:
            self._roll()
            if self._counts[(key, kind)] >= limit:
                return False
            self._counts[(key, kind)] += 1
            return True

    def used(self, key: str, kind: str) -> int:
        with self._lock:
            self._roll()
            return self._counts[(key, kind)]


limits = DailyLimits()
