"""Sign-in codes by SMS, for Indian mobile numbers.

Two backends (CARECHAT_SMS):
- "console": development. The code is made here and only logged.
- "messagecentral": Message Central VerifyNow. It makes, sends and checks the
  code on its own DLT-registered template, so CareChat needs no TRAI DLT
  registration. About Rs 0.20 per code.

Every code sent costs money, so sending is limited per number, per network
address and per day in total (see api.py).
"""

from __future__ import annotations

import base64
import logging
import re
import threading
import time

import httpx

from . import auth
from .config import settings

log = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"^[6-9]\d{9}$")


class SmsError(Exception):
    """A problem sending or checking a code, with a message safe to show."""


def normalize_phone(raw: str) -> str | None:
    """Return +91XXXXXXXXXX for an Indian mobile number, or None."""
    digits = re.sub(r"[\s\-()]", "", raw or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return f"+91{digits}" if _PHONE_RE.match(digits) else None


# --- console (development) ------------------------------------------------------

outbox: list[dict[str, str]] = []


def _console_start(phone: str) -> str:
    code = auth.new_email_code(f"phone:{phone}")
    log.info("SMS (console) to %s: CareChat code %s", phone[:5] + "*****", code)
    outbox.append({"to": phone, "code": code})
    del outbox[:-20]
    return code


# --- Message Central VerifyNow ------------------------------------------------------

_BASE = "https://cpaas.messagecentral.com"
_token: tuple[str, float] | None = None
_token_lock = threading.Lock()
# phone -> (verification id, expiry); kept only in memory, like email codes.
_pending: dict[str, tuple[str, float]] = {}


async def _mc_token(client: httpx.AsyncClient) -> str:
    global _token
    with _token_lock:
        if _token and _token[1] > time.time():
            return _token[0]
    r = await client.get(f"{_BASE}/auth/v1/authentication/token", params={
        "customerId": settings.mc_customer_id,
        "key": base64.b64encode(settings.mc_password.encode()).decode(),
        "scope": "NEW",
        "country": "91",
    }, headers={"accept": "*/*"})
    r.raise_for_status()
    token = r.json().get("token")
    if not token:
        raise SmsError("SMS sign-in isn't working right now. Please use email instead.")
    with _token_lock:
        _token = (token, time.time() + 6 * 3600)
    return token


async def _mc_start(phone: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        token = await _mc_token(client)
        r = await client.post(f"{_BASE}/verification/v3/send", params={
            "countryCode": "91",
            "customerId": settings.mc_customer_id,
            "flowType": "SMS",
            "mobileNumber": phone[3:],
            "otpLength": 6,
        }, headers={"authToken": token})
    body = _json(r)
    data = body.get("data") or {}
    if r.status_code == 200 and data.get("verificationId"):
        _pending[phone] = (str(data["verificationId"]), time.time() + 600)
        return
    log.warning("Message Central send failed: status=%s code=%s", r.status_code, body.get("responseCode"))
    if str(body.get("responseCode")) == "506":
        raise SmsError("A code was sent a moment ago. Please wait a minute before asking again.")
    if str(body.get("responseCode")) == "800":
        raise SmsError("Too many codes for this number. Please try again later or use email.")
    raise SmsError("We couldn't send a code to this number. Please check it or use email instead.")


async def _mc_check(phone: str, code: str) -> bool:
    entry = _pending.get(phone)
    if not entry or entry[1] < time.time():
        _pending.pop(phone, None)
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        token = await _mc_token(client)
        r = await client.get(f"{_BASE}/verification/v3/validateOtp", params={
            "verificationId": entry[0], "code": code.strip(),
        }, headers={"authToken": token})
    body = _json(r)
    status = (body.get("data") or {}).get("verificationStatus")
    if r.status_code == 200 and status == "VERIFICATION_COMPLETED":
        _pending.pop(phone, None)
        return True
    return False


def _json(r: httpx.Response) -> dict:
    try:
        out = r.json()
        return out if isinstance(out, dict) else {}
    except ValueError:
        return {}


# --- public ----------------------------------------------------------------------

def enabled() -> bool:
    if settings.sms_backend == "messagecentral":
        return bool(settings.mc_customer_id and settings.mc_password)
    return settings.sms_backend == "console"


async def send_code(phone: str) -> str | None:
    """Send a sign-in code. Returns the code only in console mode (for local testing)."""
    if settings.sms_backend == "messagecentral":
        try:
            await _mc_start(phone)
        except httpx.HTTPError as exc:
            log.warning("Message Central unreachable: %s", type(exc).__name__)
            raise SmsError("SMS sign-in isn't working right now. Please use email instead.") from exc
        return None
    return _console_start(phone)


async def check_code(phone: str, code: str) -> bool:
    if settings.sms_backend == "messagecentral":
        try:
            return await _mc_check(phone, code)
        except httpx.HTTPError:
            log.warning("Message Central unreachable during check")
            return False
    return auth.check_email_code(f"phone:{phone}", code)
