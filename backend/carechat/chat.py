"""Answering a chat turn: screen, retrieve, then stream Claude's answer."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, Field

from .config import settings
from .knowledge import KnowledgeBase, Passage
from .llm import FALLBACK_BETA, get_client
from .prompts import ANSWER_SYSTEM
from .reports import Report
from .safety import FIXED_MESSAGES, REGION, Verdict, screen

log = logging.getLogger(__name__)

REFUSAL_MESSAGE = (
    "I can't help with that one. I can explain your report, answer general health questions, "
    "or help you prepare questions for your doctor."
)
ERROR_MESSAGE = "Something went wrong on our side. Please try again in a moment."


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    report_id: str | None = None


def format_report(report: Report) -> str:
    lines = []
    if report.report_type:
        lines.append(f"Report type: {report.report_type}")
    if report.report_date:
        lines.append(f"Date: {report.report_date}")
    if report.results:
        lines.append("Results (test | value | unit | reference range | flag on report):")
        for r in report.results:
            lines.append(
                f"- {r.test_name} | {r.value} | {r.unit or '-'} | {r.reference_range or '-'} | {r.flag}"
            )
    if report.other_findings:
        lines.append("Other text from the report:")
        lines.extend(f"- {f}" for f in report.other_findings)
    return "\n".join(lines)


def format_sources(passages: list[Passage]) -> str:
    return "\n\n".join(
        f'<source index="{i}" title="{p.title}" url="{p.url}">\n{p.text}\n</source>'
        for i, p in enumerate(passages, start=1)
    )


def build_messages(request: ChatRequest, report: Report | None, passages: list[Passage]) -> list[dict[str, Any]]:
    history = request.messages[-settings.max_history_messages :]
    # The API needs the conversation to start with a user turn.
    while history and history[0].role != "user":
        history = history[1:]
    messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in history[:-1]]
    parts = []
    if report is not None:
        parts.append(f"<report>\n{format_report(report)}\n</report>")
    if passages:
        parts.append(f"<sources>\n{format_sources(passages)}\n</sources>")
    parts.append(f"<question>\n{history[-1].content}\n</question>")
    messages.append({"role": "user", "content": "\n\n".join(parts)})
    return messages


def validate_request(request: ChatRequest) -> str | None:
    """Return an error message for a malformed conversation, or None."""
    if request.messages[-1].role != "user":
        return "The last message must come from the user."
    if any(len(m.content) > settings.max_message_chars for m in request.messages):
        return f"Messages can be at most {settings.max_message_chars} characters."
    return None


async def answer(
    request: ChatRequest, report: Report | None, kb: KnowledgeBase
) -> AsyncIterator[dict[str, Any]]:
    """Yield events: safety, sources, text deltas, then done."""
    user_texts = [m.content for m in request.messages if m.role == "user"]
    verdict = await screen(user_texts)
    if verdict is not Verdict.OK:
        call = REGION.crisis_number if verdict is Verdict.SELF_HARM else REGION.emergency_number
        yield {"type": "safety", "verdict": verdict.value, "message": FIXED_MESSAGES[verdict], "call": call}
        yield {"type": "done"}
        return

    passages = kb.search(user_texts[-1])
    yield {
        "type": "sources",
        "sources": [{"index": i, "title": p.title, "url": p.url} for i, p in enumerate(passages, start=1)],
    }

    kwargs: dict[str, Any] = {}
    if settings.use_fallbacks:
        kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    try:
        async with get_client().beta.messages.stream(
            model=settings.answer_model,
            max_tokens=8000,
            system=ANSWER_SYSTEM,
            output_config={"effort": "low"},
            messages=build_messages(request, report, passages),
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "text", "text": text}
            final = await stream.get_final_message()
    except anthropic.APIError:
        log.exception("Answer model call failed")
        yield {"type": "error", "message": ERROR_MESSAGE}
        yield {"type": "done"}
        return

    if final.stop_reason == "refusal":
        # Discard any partial text the client has shown and replace it.
        yield {"type": "replace", "text": REFUSAL_MESSAGE}
    elif final.stop_reason == "max_tokens":
        yield {"type": "text", "text": "\n\n(Answer cut short. Ask me to continue.)"}
    yield {"type": "done"}
