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
from .redact import redact_identifiers
from .reports import Report
from .languages import LANGUAGES, language_name
from .safety import REGION, Verdict, fixed_message, screen
from .usage import log_usage

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
    # Code from languages.LANGUAGES, e.g. "ta". None means reply in the user's language.
    language: str | None = None


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


CACHE = {"type": "ephemeral"}
TRIM_NOTE = " [earlier answer trimmed]"


def _history_text(m: ChatMessage) -> str:
    """Trim long past answers. Depends only on the message itself, so the result is
    the same on every request and the cached prefix stays valid."""
    limit = settings.max_assistant_chars_in_history
    if m.role == "assistant" and len(m.content) > limit:
        return m.content[:limit] + TRIM_NOTE
    return m.content


def build_system(report: Report | None) -> list[dict[str, Any]]:
    """Fixed instructions, then the report, each cached.

    The report sits in the system prompt rather than in each question so it is
    sent once per conversation and read from cache on every follow-up.
    """
    blocks: list[dict[str, Any]] = [{"type": "text", "text": ANSWER_SYSTEM, "cache_control": CACHE}]
    if report is not None:
        blocks.append(
            {
                "type": "text",
                "text": f"The user's uploaded report (identifiers removed):\n<report>\n{format_report(report)}\n</report>",
                "cache_control": CACHE,
            }
        )
    return blocks


def build_messages(request: ChatRequest, passages: list[Passage]) -> list[dict[str, Any]]:
    history = request.messages[-settings.max_history_messages :]
    # The API needs the conversation to start with a user turn.
    while history and history[0].role != "user":
        history = history[1:]
    messages: list[dict[str, Any]] = [{"role": m.role, "content": _history_text(m)} for m in history[:-1]]
    if messages:
        # Cache breakpoint at the end of the earlier conversation. The next request
        # repeats this prefix exactly, so it is read from cache at a tenth of the price.
        last = messages[-1]
        last["content"] = [{"type": "text", "text": last["content"], "cache_control": CACHE}]
    parts = []
    if passages:
        parts.append(f"<sources>\n{format_sources(passages)}\n</sources>")
    name = language_name(request.language)
    if name and name != "English":
        parts.append(f"<reply_language>{name}</reply_language>")
    parts.append(f"<question>\n{history[-1].content}\n</question>")
    messages.append({"role": "user", "content": "\n\n".join(parts)})
    return messages


def validate_request(request: ChatRequest) -> str | None:
    """Return an error message for a malformed conversation, or None."""
    if request.language is not None and request.language not in LANGUAGES:
        return "Unknown language."
    if request.messages[-1].role != "user":
        return "The last message must come from the user."
    if any(len(m.content) > settings.max_message_chars for m in request.messages):
        return f"Messages can be at most {settings.max_message_chars} characters."
    return None


async def answer(
    request: ChatRequest, report: Report | None, kb: KnowledgeBase
) -> AsyncIterator[dict[str, Any]]:
    """Yield events: safety, sources, text deltas, then done."""
    # Strip phone numbers, emails and ID numbers before anything is sent to Claude.
    request = ChatRequest(
        messages=[ChatMessage(role=m.role, content=redact_identifiers(m.content)) for m in request.messages],
        report_id=request.report_id,
        language=request.language,
    )
    user_texts = [m.content for m in request.messages if m.role == "user"]
    verdict = await screen(user_texts)
    if verdict is not Verdict.OK:
        call = REGION.crisis_number if verdict is Verdict.SELF_HARM else REGION.emergency_number
        yield {"type": "safety", "verdict": verdict.value, "message": fixed_message(verdict, request.language), "call": call}
        yield {"type": "done"}
        return

    passages = kb.search(user_texts[-1], k=settings.max_sources)
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
            max_tokens=settings.answer_max_tokens,
            system=build_system(report),
            output_config={"effort": "low"},
            messages=build_messages(request, passages),
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "text", "text": text}
            final = await stream.get_final_message()
        log_usage("answer", settings.answer_model, getattr(final, "usage", None))
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
