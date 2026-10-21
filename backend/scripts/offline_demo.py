"""Run CareChat with a stand-in for Claude, so you can click through the app
without an API key or any cost. Answers and report readings are canned.

    cd backend && CARECHAT_AUTH_MODE=dev python -m scripts.offline_demo
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CARECHAT_AUTH_MODE", "dev")
os.environ.setdefault("CARECHAT_INPROCESS_JOBS", "false")

from carechat import chat, reports, safety, summary  # noqa: E402
from carechat.reports import LabResult, Report  # noqa: E402
from carechat.summary import FlaggedNote, Summary  # noqa: E402

SAMPLE = Report(
    is_medical_report=True, report_type="Diabetes and thyroid panel", report_date="12/09/2026", patient_age="46 Y",
    patient_sex="male",
    results=[
        LabResult(test_name="HbA1c", value="6.4", unit="%", reference_range="4.0-5.6", flag="high"),
        LabResult(test_name="Fasting glucose", value="118", unit="mg/dL", reference_range="70-99", flag="high"),
        LabResult(test_name="TSH", value="2.1", unit="uIU/mL", reference_range="0.4-4.0", flag="not_flagged"),
        LabResult(test_name="Hemoglobin", value="13.9", unit="g/dL", reference_range="13-17", flag="not_flagged"),
        LabResult(test_name="Vitamin D", value="18", unit="ng/mL", reference_range=None, flag="not_flagged"),
    ],
)
SUMMARY = Summary(
    overall="Most of your values are in the normal range. Two values linked to blood sugar are a little above the range on your report.",
    flagged=[
        FlaggedNote(test_name="HbA1c", meaning="Your HbA1c of 6.4% is in the range often seen in pre-diabetes [1]. Only your doctor can confirm this."),
        FlaggedNote(test_name="Fasting glucose", meaning="Your fasting sugar is a little above the report's range. One reading alone doesn't confirm anything."),
    ],
    doctor_questions=["Should I repeat the HbA1c test, and when?", "Is my vitamin D level something to treat?"],
    general_tips=["Regular walking and fewer sugary drinks help most people; check with your doctor."],
)
ANSWER = ("HbA1c shows your **average blood sugar over about 3 months** [1]. "
          "Yours is 6.4%, which is above the range on your report. Please talk to your doctor about what it means for you.")


class _Stream:
    def __init__(self, text: str) -> None:
        self.text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            for word in self.text.split(" "):
                await asyncio.sleep(0.03)
                yield word + " "
        return gen()

    async def get_final_message(self):
        return SimpleNamespace(stop_reason="end_turn", usage=None)


async def _parse(**kwargs):
    await asyncio.sleep(1)
    out = SUMMARY if kwargs["output_format"] is Summary else SAMPLE
    return SimpleNamespace(stop_reason="end_turn", parsed_output=out.model_copy(deep=True), usage=None)


async def _safety(**kwargs):
    return SimpleNamespace(stop_reason="end_turn", parsed_output=SimpleNamespace(label="ok"), usage=None)


FAKE = SimpleNamespace(
    messages=SimpleNamespace(parse=_safety),
    beta=SimpleNamespace(messages=SimpleNamespace(parse=_parse, stream=lambda **kw: _Stream(ANSWER))),
)
for module in (chat, reports, safety, summary):
    module.get_client = lambda: FAKE

if __name__ == "__main__":
    import uvicorn

    from carechat.main import app

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
