"""Reading uploaded medical reports into structured results."""

from __future__ import annotations

import base64
import logging
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .config import settings
from .llm import FALLBACK_BETA, get_client

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
    report_type: str | None = Field(default=None, description="e.g. 'Complete blood count', 'Discharge summary'")
    report_date: str | None = Field(default=None, description="Collection or report date as printed, or null")
    results: list[LabResult] = Field(default_factory=list)
    other_findings: list[str] = Field(
        default_factory=list,
        description="Short quotes of other important text: impressions, diagnoses listed, follow-up instructions",
    )


EXTRACT_SYSTEM = """You read medical reports and copy their contents into a structured form.
Copy names, values, units, ranges and flags exactly as printed. Never compute, guess or correct \
a value, and never add a flag the report does not show. Leave out names, addresses, phone \
numbers, record numbers and other identifiers of the patient or clinicians."""

PDF_MAGIC = b"%PDF-"


class ReportError(Exception):
    """A problem the user can fix, with a message safe to show them."""


def validate_pdf(data: bytes) -> None:
    if not data:
        raise ReportError("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ReportError(f"The file is too large. The limit is {settings.max_upload_bytes // (1024 * 1024)} MB.")
    if not data.startswith(PDF_MAGIC):
        raise ReportError("Please upload a PDF file.")


async def extract_report(pdf_bytes: bytes) -> Report:
    validate_pdf(pdf_bytes)
    kwargs = {}
    if settings.use_fallbacks:
        kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    try:
        response = await get_client().beta.messages.parse(
            model=settings.answer_model,
            max_tokens=16000,
            system=EXTRACT_SYSTEM,
            output_config={"effort": "low"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": "Extract this report."},
                    ],
                }
            ],
            output_format=Report,
            **kwargs,
        )
    except anthropic.BadRequestError as exc:
        log.warning("Report extraction rejected: %s", exc.message)
        raise ReportError("We couldn't read that PDF. Try a different file.") from exc
    if response.stop_reason == "refusal":
        raise ReportError("We couldn't read that report. Try a different file.")
    if response.stop_reason == "max_tokens":
        raise ReportError("That report is too long to read in one go. Try uploading fewer pages.")
    report = response.parsed_output
    if report is None:
        raise ReportError("We couldn't read that report. Try a different file.")
    if not report.is_medical_report:
        raise ReportError("That file doesn't look like a medical report.")
    return report
