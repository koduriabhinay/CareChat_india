import logging
from types import SimpleNamespace

from carechat.chat import ChatMessage, ChatRequest, TRIM_NOTE, build_messages, build_system
from carechat.config import settings
from carechat.knowledge import Passage
from carechat.reports import compact_text
from carechat.usage import log_usage

CACHE = {"type": "ephemeral"}


def convo(n_pairs: int, answer: str = "ok") -> list[ChatMessage]:
    msgs = []
    for i in range(n_pairs):
        msgs += [ChatMessage(role="user", content=f"q{i}"), ChatMessage(role="assistant", content=answer)]
    return msgs + [ChatMessage(role="user", content="latest")]


def test_system_prompt_and_report_are_cached():
    blocks = build_system("HbA1c | 6.1 | % | 4.0-5.6 | high", "Diet type: vegetarian")
    assert len(blocks) == 2 and "<person>" in blocks[1]["text"] and all(b["cache_control"] == CACHE for b in blocks)
    assert len(build_system(None)) == 1


def test_history_gets_one_breakpoint_at_its_end():
    msgs = build_messages(ChatRequest(messages=convo(2)), [])
    marked = [m for m in msgs if isinstance(m["content"], list)]
    assert marked == [msgs[-2]] and msgs[-2]["content"][0]["cache_control"] == CACHE


def test_cached_prefix_is_identical_on_the_next_turn():
    first = build_messages(ChatRequest(messages=convo(1)), [])
    second = build_messages(ChatRequest(messages=convo(2)), [])
    # Turn 1's history (q0, answer) must reappear byte for byte in turn 2.
    strip = lambda m: m["content"][0]["text"] if isinstance(m["content"], list) else m["content"]
    assert [strip(m) for m in first[:-1]] == [strip(m) for m in second[: len(first) - 1]]


def test_history_window_and_trimming():
    long_answer = "x" * (settings.max_assistant_chars_in_history + 500)
    msgs = build_messages(ChatRequest(messages=convo(20, long_answer)), [])
    assert len(msgs) <= settings.max_history_messages
    assistant = [m for m in msgs if m["role"] == "assistant"]
    text = assistant[0]["content"] if isinstance(assistant[0]["content"], str) else assistant[0]["content"][0]["text"]
    assert text.endswith(TRIM_NOTE) and len(text) == settings.max_assistant_chars_in_history + len(TRIM_NOTE)


def test_sources_and_language_only_in_latest_turn():
    p = Passage(title="T", url="https://medlineplus.gov/t", text="body")
    msgs = build_messages(ChatRequest(messages=convo(1), language="ta"), [p])
    assert "<sources>" in msgs[-1]["content"] and "Tamil" in msgs[-1]["content"]
    assert all("<sources>" not in str(m["content"]) for m in msgs[:-1])


def test_compact_text_shrinks_layout_whitespace():
    raw = "Glucose, fasting     112      mg/dL     70-99             H\n\n\n   Sodium   139  \n"
    out = compact_text(raw)
    assert out == "Glucose, fasting | 112 | mg/dL | 70-99 | H\nSodium | 139"
    assert len(out) < len(raw) * 0.75


def test_usage_logging(caplog):
    usage = SimpleNamespace(input_tokens=100, cache_read_input_tokens=900, cache_creation_input_tokens=0, output_tokens=50)
    with caplog.at_level(logging.INFO, logger="carechat.tokens"):
        counts = log_usage("answer", "claude-sonnet-5-5", usage)
    assert counts == {"input": 100, "cache_read": 900, "cache_write": 0, "output": 50}
    assert "cache_read=900" in caplog.text
    assert log_usage("answer", "m", None)["input"] == 0
