"""Reading uploaded medical reports into structured results.

Text PDFs are read here into text, identifiers are removed, and only the
redacted text goes to Claude. Photos of paper reports go to Claude as images
(after the user has blacked out their name and ID in the app), because there
is no text to redact; every text field Claude returns is redacted again.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .config import settings
from .llm import FALLBACK_BETA, get_client
from .redact import pdf_text, redact, redact_names
from .usage import log_usage

log = logging.getLogger(__name__)


class LabResult(BaseModel):
    test_name: str = Field(description="Test name exactly as printed on the report")
    value: str = Field(description="Result value exactly as printed, e.g. '5.8' or 'Negative'")
    unit: str | None = Field(default=None, description="Unit as printed, or null")
    reference_range: str | None = Field(default=None, description="Reference range as printed, or null")
    flag: Literal["normal", "low", "high", "abnormal", "critical", "not_flagged"] = Field(
        description="The flag the report itself prints for this result. Use not_flagged when the report shows none."
    )


class Report(BaseModel):
    is_medical_report: bool = Field(description="False if the document is not a medical report")
    report_type: str | None = Field(default=None, description="e.g. 'Complete blood count', 'Lipid profile'")
    report_date: str | None = Field(default=None, description="Collection or report date as printed, or null")
    patient_age: str | None = Field(default=None, description="Patient age as printed, e.g. '54 Y', or null")
    patient_sex: Literal["male", "female", "other"] | None = Field(default=None, description="Sex as printed, or null")
    results: list[LabResult] = Field(default_factory=list)
    other_findings: list[str] = Field(
        default_factory=list,
        description="Short quotes of other important text: impressions, follow-up instructions. No identifiers.",
    )
    unreadable: bool = Field(
        default=False, description="True if the image is too blurred, dark or cut off to read the values reliably"
    )


EXTRACT_SYSTEM = """You read medical lab reports and copy their contents into a structured form.
Copy test names, values, units, ranges and flags exactly as printed. Never compute, guess or correct \
a value, and never add a flag the report does not show. If a value can't be read clearly, leave that \
test out rather than guess, and set unreadable to true if most values can't be read.
Never copy names, addresses, phone numbers, ID or record numbers, lab or hospital names, or doctors' \
names. Identifiers in text input have already been replaced with [REDACTED]; leave them out."""

PDF_MAGIC = b"%PDF-"
IMAGE_TYPES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}
# Below this many characters of text we treat the PDF as a scan.
MIN_TEXT_CHARS = 40


class ReportError(Exception):
    """A problem the user can fix, with a message safe to show them."""

    def __init__(self, message: str, code: str = "unreadable") -> None:
        super().__init__(message)
        self.code = code


def compact_text(text: str) -> str:
    """Shrink layout whitespace, which costs tokens but carries no meaning."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]{2,}", " | ", line.strip())
        if line:
            lines.append(line)
    return "\n".join(lines)


def detect_kind(data: bytes) -> tuple[str, str]:
    """Return ("pdf"|"image", media type) or raise ReportError."""
    if not data:
        raise ReportError("The file is empty.", "empty")
    if len(data) > settings.max_upload_bytes:
        raise ReportError(
            f"The file is too large. The limit is {settings.max_upload_bytes // (1024 * 1024)} MB.", "too_large"
        )
    if data.startswith(PDF_MAGIC):
        return "pdf", "application/pdf"
    for magic, media in IMAGE_TYPES.items():
        if data.startswith(magic):
            return "image", media
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image", "image/webp"
    raise ReportError("Please upload a PDF or a photo (JPG or PNG).", "bad_type")


def validate_pdf(data: bytes) -> None:
    kind, _ = detect_kind(data)
    if kind != "pdf":
        raise ReportError("Please upload a PDF file.", "bad_type")


def prepare_pdf_text(data: bytes, known_names: list[str] | None = None) -> tuple[str, str]:
    """Return (raw text, redacted compact text). Raw text never leaves the server."""
    text = pdf_text(data)
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise ReportError(
            "This PDF is a scan with no text in it. Please take a photo of the paper report instead, "
            "and black out your name before sending.",
            "scanned_pdf",
        )
    return text, compact_text(redact_names(redact(text), known_names or []))


def _clean(report: Report, known_names: list[str]) -> Report:
    """Redact every text field Claude returned, in case an identifier slipped through."""
    def scrub(value: str | None) -> str | None:
        return redact_names(redact(value), known_names) if value else value

    report.report_type = scrub(report.report_type)
    report.other_findings = [scrub(f) or "" for f in report.other_findings]
    for r in report.results:
        r.test_name = scrub(r.test_name) or r.test_name
    return report


async def _parse(content: list[dict] | str) -> Report:
    kwargs = {}
    if settings.use_fallbacks:
        kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    try:
        response = await get_client().beta.messages.parse(
            model=settings.answer_model,
            max_tokens=settings.extract_max_tokens,
            system=EXTRACT_SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": content}],
            output_format=Report,
            **kwargs,
        )
    except anthropic.BadRequestError as exc:
        log.warning("Report extraction rejected: %s", exc.message)
        raise ReportError("We couldn't read that file. Try a different one.") from exc
    log_usage("extract", settings.answer_model, getattr(response, "usage", None))
    if response.stop_reason == "refusal":
        raise ReportError("We couldn't read that report. Try a different file.")
    if response.stop_reason == "max_tokens":
        raise ReportError("That report is too long to read in one go. Try uploading fewer pages.", "too_long")
    report = response.parsed_output
    if report is None:
        raise ReportError("We couldn't read that report. Try a different file.")
    if not report.is_medical_report:
        raise ReportError("That doesn't look like a medical report.", "not_medical")
    if report.unreadable or not report.results:
        raise ReportError(
            "We couldn't read the values clearly. Take the photo again in good light, flat and in focus.", "blurry"
        )
    return report


async def extract_from_text(redacted_text: str, known_names: list[str] | None = None) -> Report:
    content = f"<report_text>\n{redacted_text}\n</report_text>\n\nExtract this report."
    return _clean(await _parse(content), known_names or [])


async def extract_from_image(data: bytes, media_type: str, known_names: list[str] | None = None) -> Report:
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}},
        {"type": "text", "text": "This is a photo of a lab report. Extract it."},
    ]
    return _clean(await _parse(content), known_names or [])


async def extract_report(pdf_bytes: bytes) -> Report:
    """Text PDF to structured results (kept for scripts and older callers)."""
    validate_pdf(pdf_bytes)
    _, redacted = prepare_pdf_text(pdf_bytes)
    return await extract_from_text(redacted)
