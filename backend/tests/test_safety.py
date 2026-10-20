import anthropic
import httpx
import pytest

from carechat.safety import Verdict, keyword_check, screen


@pytest.mark.parametrize(
    "text",
    [
        "I have chest pain right now",
        "my dad can't breathe properly",
        "her face is drooping and she has slurred speech",
        "I think I took an overdose of my pills",
        "the bleeding won't stop",
        "my throat is closing after eating peanuts",
        "worst headache of my life",
    ],
)
def test_keywords_catch_emergencies(text):
    assert keyword_check(text) is Verdict.EMERGENCY


@pytest.mark.parametrize("text", ["I want to kill myself", "thinking about suicide", "I want to end my life"])
def test_keywords_catch_self_harm(text):
    assert keyword_check(text) is Verdict.SELF_HARM


@pytest.mark.parametrize("text", ["What is HbA1c?", "Why is my ALT high?", "What is a stroke?"])
def test_keywords_leave_normal_questions(text):
    assert keyword_check(text) is Verdict.OK


async def test_keyword_hit_skips_classifier(fake_client):
    assert await screen(["I have chest pain"]) is Verdict.EMERGENCY
    assert fake_client.calls == []


async def test_classifier_used_when_no_keyword(fake_client):
    fake_client.safety_label = "emergency"
    assert await screen(["my baby is 2 months old and has a fever of 101"]) is Verdict.EMERGENCY
    assert fake_client.calls[0][0] == "safety"


async def test_classifier_failure_fails_closed(fake_client):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_client.safety_error = anthropic.APIConnectionError(request=request)
    assert await screen(["What is HbA1c?"]) is Verdict.UNAVAILABLE
