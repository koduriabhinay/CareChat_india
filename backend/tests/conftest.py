"""Test helpers: a fake Claude client so tests never call the real API."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeStream:
    def __init__(self, chunks: list[str], stop_reason: str) -> None:
        self._chunks = chunks
        self._stop_reason = stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            for c in self._chunks:
                yield c

        return gen()

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop_reason)


class FakeClient:
    """Records calls and returns canned results."""

    def __init__(self) -> None:
        self.safety_label = "ok"
        self.safety_error: Exception | None = None
        self.answer_chunks = ["Hello", " there."]
        self.answer_stop = "end_turn"
        self.report: Any = None
        self.summary: Any = None
        self.calls: list[tuple[str, dict]] = []

        async def safety_parse(**kwargs):
            self.calls.append(("safety", kwargs))
            if self.safety_error:
                raise self.safety_error
            return SimpleNamespace(
                stop_reason="end_turn", parsed_output=SimpleNamespace(label=self.safety_label)
            )

        async def report_parse(**kwargs):
            # Report extraction and the first summary share this call; route by the requested shape.
            if kwargs["output_format"].__name__ == "Summary":
                self.calls.append(("summary", kwargs))
                return SimpleNamespace(stop_reason="end_turn", parsed_output=self.summary)
            self.calls.append(("report", kwargs))
            return SimpleNamespace(stop_reason="end_turn", parsed_output=self.report)

        def answer_stream(**kwargs):
            self.calls.append(("answer", kwargs))
            return FakeStream(self.answer_chunks, self.answer_stop)

        self.messages = SimpleNamespace(parse=safety_parse)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=report_parse, stream=answer_stream))


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()
    for module in ("carechat.safety", "carechat.chat", "carechat.reports", "carechat.summary"):
        monkeypatch.setattr(f"{module}.get_client", lambda: client)
    return client


def _set(name: str, value):
    from carechat import config

    original = getattr(config.settings, name)
    object.__setattr__(config.settings, name, value)
    return original


@pytest.fixture
def db_path(tmp_path):
    """Point the app at throwaway databases and fresh in-memory counters for one test."""
    from carechat import metrics, ratelimit

    path = str(tmp_path / "test.db")
    changed = {
        "db_path": path,
        "knowledge_path": str(tmp_path / "knowledge.db"),
        "store_backend": "sqlite",
        "auth_mode": "dev",
        "mail_backend": "console",
        "run_inprocess_jobs": False,
        "cron_token": "cron-secret",
        "admin_emails": ("admin@example.com",),
    }
    originals = {k: _set(k, v) for k, v in changed.items()}
    metrics.metrics.__init__()
    ratelimit.limits.__init__()
    yield path
    for k, v in originals.items():
        _set(k, v)
