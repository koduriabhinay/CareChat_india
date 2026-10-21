"""Remove patient identifiers from report text before it leaves our server.

Reports are read locally into text, identifiers are replaced with
[REDACTED], and only the redacted text is sent to Claude. The original PDF
is never sent or stored.

This is rule-based: it catches labelled fields (Name:, UHID:, DOB: ...) and
identifier formats (phone numbers, emails, Aadhaar and ABHA numbers). It
cannot catch a name printed with no label, so keep testing it on real lab
layouts and extend the label list.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

REDACTED = "[REDACTED]"

# Field labels whose value identifies a person. Age and sex are kept because
# reference ranges depend on them.
_ID_LABELS = [
    r"patient(?:'s)? name",
    r"patient",
    r"name",
    r"pt\.? name",
    r"mr(?:n|\.? ?no\.?)",
    r"medical record (?:no\.?|number)",
    r"uhid",
    r"patient id",
    r"pid",
    r"ip(?:d)? no\.?",
    r"op(?:d)? no\.?",
    r"reg(?:istration)?\.? ?(?:no\.?|number|id)",
    r"lab (?:no\.?|number|id)",
    r"sample (?:no\.?|id)",
    r"barcode",
    r"accession (?:no\.?|number)",
    r"visit (?:no\.?|id)",
    r"d\.?o\.?b\.?",
    r"date of birth",
    r"address",
    r"(?:mobile|phone|contact|tel)(?:\.? ?no\.?)?",
    r"e-?mail",
    r"aadhaar(?: no\.?)?",
    r"abha(?: (?:no\.?|number|address|id))?",
    r"ref(?:erred)?\.? ?by",
    r"referring (?:doctor|physician)",
    r"consultant",
    r"doctor",
    r"dr\.? name",
    r"(?:father|mother|husband|guardian)(?:'s)? name",
    r"s/o|d/o|w/o|c/o",
]

# "Label: value" where the value runs to two spaces, a separator or the line end.
_LABELLED_RE = re.compile(
    r"(?im)(?<![A-Za-z])(?<!test )(?<!investigation )(?<!parameter )(" + "|".join(_ID_LABELS) + r")(\s*[:\-]\s*)(.+?)(?=\s{2,}|\s*\||\s*\t|$)"
)

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"(?<!\d)\d{2}-\d{4}-\d{4}-\d{4}(?!\d)"),  # ABHA number
    re.compile(r"(?<!\d)\d{4}[ -]\d{4}[ -]\d{4}(?!\d)"),  # Aadhaar (spaced)
    re.compile(r"(?<!\d)\d{12}(?!\d)"),  # Aadhaar (unspaced)
    re.compile(r"(?<![\d.])(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?![\d.])"),  # Indian mobile
    re.compile(r"(?i)\b[\w.-]+@(?:abdm|sbx)\b"),  # ABHA address
]

# A name prefixed by a title, e.g. "Mr. Ravi Kumar" or "Dr Priya Shah".
_TITLED_NAME_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Master|Baby|Dr|Smt|Shri|Kumari)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z.]+){0,3}")


def redact_identifiers(text: str) -> str:
    """Lighter pass for chat messages: ID formats only (phones, emails, Aadhaar, ABHA)."""
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact(text: str) -> str:
    text = _LABELLED_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _TITLED_NAME_RE.sub(REDACTED, text)
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def pdf_text(data: bytes) -> str:
    """Text layer of a PDF, or an empty string if it has none (e.g. a scan)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError):
        return ""


_NAME_LABEL_RE = re.compile(
    r"(?im)(?<![A-Za-z])(?:patient(?:'s)? name|pt\.? name|patient|name)\s*[:\-]\s*(.+?)(?=\s{2,}|\s*\||\s*\t|$)"
)
_TITLE_RE = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Master|Baby|Dr|Smt|Shri|Kumari)\.?\s+", re.I)


def printed_name(text: str) -> str | None:
    """The patient name printed on a report, read locally to suggest whose report it is.

    It is used only on our server to match a family profile and is never sent to Claude.
    """
    m = _NAME_LABEL_RE.search(text)
    if not m:
        return None
    name = _TITLE_RE.sub("", m.group(1).strip())
    name = re.split(r"\s+(?:age|sex|gender)\b", name, flags=re.I)[0].strip(" ,;")
    return name or None


def redact_names(text: str, names: list[str]) -> str:
    """Remove known names (the account's profile names) wherever they appear, even unlabelled."""
    for name in sorted({n.strip() for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True):
        text = re.sub(re.escape(name), REDACTED, text, flags=re.I)
        for part in name.split():
            if len(part) >= 4:
                text = re.sub(rf"\b{re.escape(part)}\b", REDACTED, text, flags=re.I)
    return text
