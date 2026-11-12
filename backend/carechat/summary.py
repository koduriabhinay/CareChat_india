"""The plain-language summary shown right after a report is read (feature F1).

Code decides each value's status from the report's own flags and ranges
(results.py). Claude only writes the words: the overall picture, what each
flagged value means, and 2 to 3 questions for the doctor, in the user's
language, citing trusted sources where it explains a condition.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from pydantic import BaseModel, Field

from .config import settings
from .results import search_terms
from .knowledge import KnowledgeBase, Passage
from .languages import language_name
from .llm import FALLBACK_BETA, get_client
from .usage import log_usage

log = logging.getLogger(__name__)


class FlaggedNote(BaseModel):
    test_name: str = Field(description="Test name exactly as in the table")
    meaning: str = Field(description="1-3 plain sentences on what this result can mean, cautious, never a diagnosis")


class Summary(BaseModel):
    overall: str = Field(description="2-4 plain sentences: the overall picture of this report")
    flagged: list[FlaggedNote] = Field(default_factory=list, description="One note per value not in the normal range")
    doctor_questions: list[str] = Field(description="2 or 3 short questions to ask the doctor")
    general_tips: list[str] = Field(
        default_factory=list,
        description="At most 3 general diet or lifestyle tips, each ending with a reminder to check with the doctor",
    )


SUMMARY_SYSTEM = """You write the first summary a patient sees after uploading a lab report to CareChat, \
a patient education app in India. Many readers have little schooling and read on a phone.

Rules:
- Use only the values, ranges and statuses in the <results> table. The status column was computed from \
the report's own flags and ranges; never change it and never use a range you remember.
- Never say the person has a disease. When a result is often linked to a condition, use cautious words, \
for example: "Your HbA1c of 6.4% is in the range often seen in pre-diabetes. Only your doctor can confirm \
this." and cite a numbered source like [1] from <sources> when you do. If no source covers it, describe \
what the test measures without naming a condition.
- Never suggest starting, stopping or changing any medicine, supplement or dose.
- Write a flagged note for every result whose status is low, high, abnormal or critical. Skip normal ones.
- Doctor questions: 2 or 3, short, specific to this report.
- General tips: only general, widely accepted diet or lifestyle guidance that fits the person's diet type \
if given, each ending with "check with your doctor". Leave the list empty if nothing fits.
- Plain words a 12-year-old could follow. Explain any medical term in simple words.
- Language: write every field in the language named in <reply_language>, in its usual script. Keep test \
names, numbers and units exactly as printed."""


def _profile_context(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    parts = []
    for key, label in (("age", "Age"), ("sex", "Sex"), ("diet_type", "Diet"), ("pregnant", "Pregnant"),
                       ("conditions", "Known conditions"), ("medicines", "Current medicines")):
        value = profile.get(key)
        if value in (None, "", [], False):
            continue
        parts.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    return "\n".join(parts)


def format_rows(rows: list[dict[str, Any]]) -> str:
    lines = ["test | value | unit | report's range | status"]
    for r in rows:
        status = "range not given on report" if r["status"] == "no_range" else r["status"]
        lines.append(f"{r['test_name']} | {r['value']} | {r.get('unit') or '-'} | {r.get('reference_range') or '-'} | {status}")
    return "\n".join(lines)


def sources_for(rows: list[dict[str, Any]], kb: KnowledgeBase) -> list[Passage]:
    flagged = [r["test_name"] for r in rows if r["status"] in ("low", "high", "abnormal", "critical")]
    seen: dict[str, Passage] = {}
    for name in flagged[:4]:
        for p in kb.search(search_terms(name), k=1):
            seen.setdefault(p.url + p.text[:40], p)
    return list(seen.values())[: settings.max_sources]


async def write_summary(
    rows: list[dict[str, Any]], report_type: str | None, language: str | None,
    profile: dict[str, Any] | None, kb: KnowledgeBase,
) -> tuple[Summary, list[Passage]]:
    passages = sources_for(rows, kb)
    parts = []
    if report_type:
        parts.append(f"<report_type>{report_type}</report_type>")
    context = _profile_context(profile)
    if context:
        parts.append(f"<person>\n{context}\n</person>")
    parts.append(f"<results>\n{format_rows(rows)}\n</results>")
    if passages:
        parts.append("<sources>\n" + "\n\n".join(
            f'<source index="{i}" title="{p.title}">\n{p.text}\n</source>' for i, p in enumerate(passages, start=1)
        ) + "\n</sources>")
    parts.append(f"<reply_language>{language_name(language) or 'English'}</reply_language>")
    kwargs: dict[str, Any] = {}
    if settings.use_fallbacks:
        kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    try:
        response = await get_client().beta.messages.parse(
            model=settings.answer_model,
            max_tokens=settings.summary_max_tokens,
            system=[{"type": "text", "text": SUMMARY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "\n\n".join(parts)}],
            output_format=Summary,
            **kwargs,
        )
    except anthropic.APIError as exc:
        raise SummaryError("The summary couldn't be written right now.") from exc
    log_usage("summary", settings.answer_model, getattr(response, "usage", None))
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise SummaryError("The summary couldn't be written for this report.")
    return response.parsed_output, passages


class SummaryError(Exception):
    pass
