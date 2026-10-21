"""Everything numeric is done here, in code, never by the AI.

- Status of each value (low / normal / high) from the flag and range printed
  on the report.
- Critical values that must show the fixed emergency message first.
- Matching the same test across labs (names and units) for trends.
- Trend changes between visits.
- BMI with the cut-offs used for Asian Indian adults.

The thresholds marked DRAFT need sign-off by a clinician before launch.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

Status = Literal["low", "normal", "high", "abnormal", "critical", "no_range", "see_report"]

_NUM = re.compile(r"^[<>≤≥]?\s*(-?\d[\d,]*\.?\d*)$")


def parse_number(value: str | None) -> float | None:
    """'5.8' -> 5.8, '1,200' -> 1200. Values like '<0.5' or 'Negative' are not plain numbers."""
    if value is None:
        return None
    text = value.strip()
    if text[:1] in "<>≤≥":
        return None
    m = _NUM.match(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


_RANGE_PATTERNS = [
    (re.compile(r"^\s*(-?\d[\d,]*\.?\d*)\s*(?:-|–|—|to)\s*(-?\d[\d,]*\.?\d*)\s*$", re.I), "between"),
    (re.compile(r"^\s*(?:<|≤|<=|up\s*to|upto|less than|below)\s*(\d[\d,]*\.?\d*)\s*$", re.I), "max"),
    (re.compile(r"^\s*(?:>|≥|>=|more than|above|greater than)\s*(\d[\d,]*\.?\d*)\s*$", re.I), "min"),
]


def parse_range(text: str | None) -> tuple[float | None, float | None] | None:
    """Parse a printed reference range into (low, high). None when it can't be read."""
    if not text:
        return None
    cleaned = re.sub(r"[a-zA-Z/%µμ]+\s*$", "", text.strip()).strip()  # drop a trailing unit
    for pattern, kind in _RANGE_PATTERNS:
        m = pattern.match(cleaned) or pattern.match(text.strip())
        if not m:
            continue
        nums = [float(g.replace(",", "")) for g in m.groups()]
        if kind == "between":
            return (nums[0], nums[1])
        if kind == "max":
            return (None, nums[0])
        return (nums[0], None)
    return None


def status_for(value: str, reference_range: str | None, printed_flag: str) -> Status:
    """Use the report's own flag first, then its own range. Never a remembered range."""
    if printed_flag in ("low", "high", "critical", "abnormal"):
        return printed_flag  # type: ignore[return-value]
    number = parse_number(value)
    bounds = parse_range(reference_range)
    if bounds is not None and number is not None:
        low, high = bounds
        if low is not None and number < low:
            return "low"
        if high is not None and number > high:
            return "high"
        return "normal"
    if printed_flag == "normal":
        return "normal"
    if not reference_range:
        return "no_range"
    return "see_report"


# --- Matching tests across labs ------------------------------------------------

_ALIASES: dict[str, list[str]] = {
    "hba1c": ["hba1c", "glycated hemoglobin", "glycated haemoglobin", "glycosylated hemoglobin",
              "glycosylated haemoglobin", "hemoglobin a1c", "haemoglobin a1c", "a1c"],
    "glucose_fasting": ["fasting blood sugar", "fbs", "fasting plasma glucose", "glucose fasting",
                        "blood sugar fasting", "fasting glucose", "plasma glucose fasting", "glucose (fasting)"],
    "glucose_pp": ["post prandial blood sugar", "ppbs", "glucose pp", "post prandial glucose",
                   "blood sugar pp", "glucose post prandial", "glucose (pp)"],
    "glucose_random": ["random blood sugar", "rbs", "glucose random", "random glucose"],
    "hemoglobin": ["hemoglobin", "haemoglobin", "hb", "hgb"],
    "tsh": ["tsh", "thyroid stimulating hormone", "tsh ultrasensitive", "ultrasensitive tsh"],
    "creatinine": ["creatinine", "serum creatinine", "s creatinine", "creatinine serum"],
    "urea": ["urea", "blood urea", "serum urea"],
    "uric_acid": ["uric acid", "serum uric acid"],
    "cholesterol_total": ["total cholesterol", "cholesterol total", "cholesterol", "serum cholesterol"],
    "ldl": ["ldl", "ldl cholesterol", "ldl-c", "ldl cholesterol direct", "ldl direct"],
    "hdl": ["hdl", "hdl cholesterol", "hdl-c", "hdl cholesterol direct"],
    "triglycerides": ["triglycerides", "triglyceride", "tg", "serum triglycerides"],
    "vitamin_d": ["vitamin d", "25 oh vitamin d", "25-oh vitamin d", "vitamin d total", "25 hydroxy vitamin d",
                  "vitamin d3", "25(oh) vitamin d"],
    "vitamin_b12": ["vitamin b12", "b12", "cyanocobalamin", "vit b12"],
    "platelets": ["platelet count", "platelets", "plt"],
    "wbc": ["total leucocyte count", "total leukocyte count", "tlc", "wbc", "wbc count", "white blood cells"],
    "potassium": ["potassium", "serum potassium", "k+", "k"],
    "sodium": ["sodium", "serum sodium", "na+", "na"],
    "alt": ["sgpt", "alt", "alanine aminotransferase", "alt (sgpt)", "sgpt (alt)"],
    "ast": ["sgot", "ast", "aspartate aminotransferase", "ast (sgot)", "sgot (ast)"],
}

_ALIAS_INDEX = {alias: key for key, names in _ALIASES.items() for alias in names}


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9()+\- ]", " ", name.lower())).strip()


def test_key(name: str) -> str:
    cleaned = _clean_name(name)
    if cleaned in _ALIAS_INDEX:
        return _ALIAS_INDEX[cleaned]
    no_paren = re.sub(r"\s*\(.*?\)\s*", " ", cleaned).strip()
    return _ALIAS_INDEX.get(no_paren, re.sub(r"[^a-z0-9]+", "_", no_paren).strip("_") or "unknown")


def search_terms(name: str) -> str:
    """The test name plus its other common names, for finding reference passages."""
    return " ".join([name, *_ALIASES.get(test_key(name), [])])


def _unit(unit: str | None) -> str:
    return (unit or "").lower().replace("μ", "u").replace("µ", "u").replace(" ", "")


# (test key, unit as printed) -> (factor to standard unit, standard unit)
_CONVERSIONS: dict[tuple[str, str], tuple[float, str]] = {
    **{(k, "mmol/l"): (18.016, "mg/dL") for k in ("glucose_fasting", "glucose_pp", "glucose_random")},
    **{(k, "mmol/l"): (38.67, "mg/dL") for k in ("cholesterol_total", "ldl", "hdl")},
    ("triglycerides", "mmol/l"): (88.57, "mg/dL"),
    ("creatinine", "umol/l"): (1 / 88.42, "mg/dL"),
    ("hemoglobin", "g/l"): (0.1, "g/dL"),
    ("vitamin_d", "nmol/l"): (1 / 2.496, "ng/mL"),
}


def standard_value(key: str, value: float, unit: str | None) -> tuple[float, str]:
    conv = _CONVERSIONS.get((key, _unit(unit)))
    if conv:
        return round(value * conv[0], 2), conv[1]
    return value, unit or ""


# --- Critical values -----------------------------------------------------------
# DRAFT: needs clinician sign-off. Applied only when the unit matches exactly.
_CRITICAL: dict[tuple[str, str], tuple[float | None, float | None]] = {
    ("potassium", "mmol/l"): (2.5, 6.5),
    ("potassium", "meq/l"): (2.5, 6.5),
    ("sodium", "mmol/l"): (120, 160),
    ("sodium", "meq/l"): (120, 160),
    ("glucose_fasting", "mg/dl"): (54, 400),
    ("glucose_random", "mg/dl"): (54, 400),
    ("glucose_pp", "mg/dl"): (54, 400),
    ("hemoglobin", "g/dl"): (7.0, None),
}


def is_critical(test_name: str, value: str, unit: str | None, printed_flag: str) -> bool:
    if printed_flag == "critical":
        return True
    number = parse_number(value)
    limits = _CRITICAL.get((test_key(test_name), _unit(unit)))
    if number is None or limits is None:
        return False
    low, high = limits
    return (low is not None and number <= low) or (high is not None and number >= high)


# --- Table rows ----------------------------------------------------------------

def table_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows for the values table: everything as printed plus a computed status."""
    rows = []
    for r in results:
        rows.append({
            "test_name": r["test_name"],
            "value": r["value"],
            "unit": r.get("unit"),
            "reference_range": r.get("reference_range"),
            "status": status_for(r["value"], r.get("reference_range"), r.get("flag", "not_flagged")),
            "critical": is_critical(r["test_name"], r["value"], r.get("unit"), r.get("flag", "not_flagged")),
            "key": test_key(r["test_name"]),
        })
    return rows


# --- Dates and trends ----------------------------------------------------------

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d %B %Y",
                 "%d/%m/%y", "%d-%m-%y", "%b %d, %Y", "%B %d, %Y", "%d %b, %Y")


def parse_report_date(text: str | None) -> date | None:
    """Indian reports print day first, so 03/04/2025 is 3 April."""
    if not text:
        return None
    candidate = re.sub(r"\s+", " ", text.strip())
    candidate = re.split(r"\s\d{1,2}:\d{2}", candidate)[0].strip()  # drop a time
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


# DRAFT: a change this large between visits shows "show this to your doctor soon".
BIG_CHANGE_PERCENT = 30.0


def build_trends(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """reports: [{"id", "date" (ISO), "rows": table_rows(...)}], any order.

    Returns one series per test with at least one numeric value, newest change computed in code.
    """
    series: dict[str, dict[str, Any]] = {}
    for rep in sorted(reports, key=lambda r: r["date"]):
        for row in rep["rows"]:
            number = parse_number(row["value"])
            if number is None:
                continue
            value, unit = standard_value(row["key"], number, row.get("unit"))
            s = series.setdefault(row["key"], {"key": row["key"], "test_name": row["test_name"], "unit": unit, "points": []})
            if unit != s["unit"]:
                continue  # can't compare different units safely
            s["points"].append({
                "report_id": rep["id"], "date": rep["date"], "value": value, "status": row["status"],
                "reference_range": row.get("reference_range"),
            })
    out = []
    for s in series.values():
        pts = s["points"]
        s["change"] = None
        if len(pts) >= 2:
            prev, last = pts[-2]["value"], pts[-1]["value"]
            diff = round(last - prev, 2)
            pct = round(diff / prev * 100, 1) if prev else None
            s["change"] = {
                "from": prev, "to": last, "difference": diff, "percent": pct,
                "direction": "up" if diff > 0 else "down" if diff < 0 else "same",
                "big": pct is not None and abs(pct) >= BIG_CHANGE_PERCENT,
            }
        out.append(s)
    out.sort(key=lambda s: (not (s["change"] or {}).get("big"), s["test_name"].lower()))
    return out


# --- BMI ---------------------------------------------------------------------

def bmi(height_cm: float | None, weight_kg: float | None) -> dict[str, Any] | None:
    """BMI with the cut-offs used for Asian Indian adults (lower than WHO's global ones)."""
    if not height_cm or not weight_kg or height_cm < 50 or weight_kg < 2:
        return None
    value = round(weight_kg / (height_cm / 100) ** 2, 1)
    if value < 18.5:
        band = "underweight"
    elif value < 23:
        band = "normal"
    elif value < 25:
        band = "overweight"
    else:
        band = "obese"
    return {"value": value, "band": band}
