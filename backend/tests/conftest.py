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
        self.calls: list[tuple[str, dict]] = []

        async def safety_parse(**kwargs):
            self.calls.append(("safety", kwargs))
            if self.safety_error:
                raise self.safety_error
            return SimpleNamespace(
                stop_reason="end_turn", parsed_output=SimpleNamespace(label=self.safety_label)
            )

        async def report_parse(**kwargs):
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
    for module in ("carechat.safety", "carechat.chat", "carechat.reports"):
        monkeypatch.setattr(f"{module}.get_client", lambda: client)
    return client


@pytest.fixture
def db_path(tmp_path):
    """Point the app at a throwaway database for one test."""
    from carechat import config

    path = str(tmp_path / "test.db")
    original = config.settings.db_path
    object.__setattr__(config.settings, "db_path", path)
    yield path
    object.__setattr__(config.settings, "db_path", original)
