"""Usage metrics for the admin dashboard and the Claude spend cap.

Counts are kept in memory and saved to the store once an hour as one record,
so metrics cost almost nothing against Catalyst's free-tier write limits.
Nothing here holds message text or who a patient is: only totals.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

# USD per million tokens: input, output, cache read, cache write (5-minute cache).
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-opus-5-5": (4.0, 20.0, 0.40, 5.0),
}
_DEFAULT_PRICE = PRICES["claude-sonnet-5-5"]


def cost_usd(model: str, counts: dict[str, int]) -> float:
    p_in, p_out, p_read, p_write = PRICES.get(model, _DEFAULT_PRICE)
    return (
        counts.get("input", 0) * p_in + counts.get("output", 0) * p_out
        + counts.get("cache_read", 0) * p_read + counts.get("cache_write", 0) * p_write
    ) / 1_000_000


def _hour_key(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H")


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset()
        self._month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        self._month_spend_saved = 0.0
        self._active_day: dict[str, dict[str, str]] = {}  # account -> {"role", "language"}
        self._active_day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _reset(self) -> None:
        self.hour = _hour_key()
        self.events: Counter[str] = Counter()
        self.tokens: dict[str, Counter[str]] = defaultdict(Counter)
        self.cost = 0.0
        self.latencies: list[float] = []

    # --- recording ---------------------------------------------------------
    def event(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.events[name] += n

    def active(self, account_id: str, role: str, language: str | None) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            if today != self._active_day_key:
                self._active_day = {}
                self._active_day_key = today
            self._active_day[account_id] = {"role": role, "language": language or "en"}

    def tokens_used(self, call: str, model: str, counts: dict[str, int]) -> None:
        with self._lock:
            for k, v in counts.items():
                self.tokens[call][k] += v
            self.cost += cost_usd(model, counts)

    def latency(self, seconds: float) -> None:
        with self._lock:
            self.latencies.append(seconds)
            del self.latencies[:-2000]

    # --- spend cap ---------------------------------------------------------
    def month_spend(self) -> float:
        with self._lock:
            return self._month_spend_saved + self.cost

    def over_budget(self) -> bool:
        return settings.monthly_budget_usd > 0 and self.month_spend() >= settings.monthly_budget_usd

    def load_month(self, saved_hours: list[dict[str, Any]]) -> None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self._lock:
            self._month_key = month
            self._month_spend_saved = sum(h.get("cost", 0.0) for h in saved_hours if h.get("hour", "").startswith(month))

    # --- saving ------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            lat = sorted(self.latencies)
            active = list(self._active_day.values())
            return {
                "hour": self.hour,
                "events": dict(self.events),
                "tokens": {k: dict(v) for k, v in self.tokens.items()},
                "cost": round(self.cost, 6),
                "latency_p50": lat[len(lat) // 2] if lat else None,
                "latency_p95": lat[int(len(lat) * 0.95)] if lat else None,
                "active_today": {
                    "total": len(active),
                    "by_role": dict(Counter(a["role"] for a in active)),
                    "by_language": dict(Counter(a["language"] for a in active)),
                },
            }

    def roll(self) -> dict[str, Any] | None:
        """Return the finished hour's snapshot to save and start a new hour. None if nothing happened."""
        snap = self.snapshot()
        with self._lock:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            if month != self._month_key:
                self._month_key = month
                self._month_spend_saved = 0.0
            else:
                self._month_spend_saved += self.cost
            self._reset()
        if not snap["events"] and not snap["tokens"]:
            return None
        return snap


metrics = Metrics()


def summarize(hours: list[dict[str, Any]], current: dict[str, Any], days: int = 30) -> dict[str, Any]:
    """Totals per day for the admin dashboard, from saved hours plus the current hour."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    per_day: dict[str, dict[str, Any]] = {}
    for h in [*hours, current]:
        day = h["hour"][:10]
        if day < cutoff:
            continue
        d = per_day.setdefault(day, {"day": day, "events": Counter(), "cost": 0.0, "tokens": Counter(), "active": 0,
                                     "latency_p95": None})
        d["events"].update(h.get("events", {}))
        d["cost"] += h.get("cost", 0.0)
        for counts in h.get("tokens", {}).values():
            d["tokens"].update(counts)
        d["active"] = max(d["active"], h.get("active_today", {}).get("total", 0))
        if h.get("latency_p95") is not None:
            d["latency_p95"] = max(d["latency_p95"] or 0, h["latency_p95"])
    days_out = []
    for d in sorted(per_day.values(), key=lambda x: x["day"]):
        days_out.append({**d, "events": dict(d["events"]), "tokens": dict(d["tokens"]), "cost": round(d["cost"], 4)})
    return {
        "days": days_out,
        "today": current.get("active_today", {}),
        "month_spend_usd": round(metrics.month_spend(), 4),
        "monthly_budget_usd": settings.monthly_budget_usd,
        "daily_caps": {"reports": settings.daily_reports_per_user, "questions": settings.daily_questions_per_user},
    }
