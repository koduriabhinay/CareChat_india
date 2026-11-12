"""Sign-in and user levels.

Three ways in:
- Guest: anyone can try CareChat without signing in. A guest's data is
  deleted after 24 hours and can't be saved as history.
- Email code: a 6-digit code sent by email.
- Google: the web app gets a Google ID token, which is checked with Google.

After sign-in the API issues its own signed session token. The token carries
the account id and level, so most requests need no database read.

User levels: patient, admin (emails in CARECHAT_ADMIN_EMAILS), and doctor
(for the case portal, a later phase; no route grants it yet).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import Depends, Header, HTTPException

from .config import settings

log = logging.getLogger(__name__)

Role = Literal["guest", "patient", "doctor", "admin"]

_secret = settings.secret_key.encode() or secrets.token_bytes(32)
if not settings.secret_key:
    log.warning("CARECHAT_SECRET_KEY is not set; sessions will end when the server restarts.")


@dataclass(frozen=True)
class Principal:
    account_id: str
    role: Role
    email: str | None = None

    @property
    def is_guest(self) -> bool:
        return self.role == "guest"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(principal: Principal, days: float | None = None) -> str:
    lifetime = (days if days is not None else settings.session_days) * 86400
    payload = {"a": principal.account_id, "r": principal.role, "e": principal.email, "x": int(time.time() + lifetime)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> Principal | None:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(_secret, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload["x"] < time.time():
            return None
        return Principal(account_id=payload["a"], role=payload["r"], email=payload.get("e"))
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def role_for_email(email: str) -> Role:
    return "admin" if email.lower() in settings.admin_emails else "patient"


# --- Email codes ---------------------------------------------------------------

_CODE_TTL = 600
_MAX_ATTEMPTS = 5
_codes: dict[str, tuple[str, float, int]] = {}
_codes_lock = threading.Lock()


def _hash(code: str) -> str:
    return hmac.new(_secret, code.encode(), hashlib.sha256).hexdigest()


def new_email_code(email: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    with _codes_lock:
        _codes[email.lower()] = (_hash(code), time.time() + _CODE_TTL, 0)
    return code


def check_email_code(email: str, code: str) -> bool:
    key = email.lower()
    with _codes_lock:
        entry = _codes.get(key)
        if not entry:
            return False
        digest, expires, attempts = entry
        if time.time() > expires or attempts >= _MAX_ATTEMPTS:
            _codes.pop(key, None)
            return False
        if hmac.compare_digest(digest, _hash(code.strip())):
            _codes.pop(key, None)
            return True
        _codes[key] = (digest, expires, attempts + 1)
        return False


# --- Google ------------------------------------------------------------------

async def verify_google_token(id_token: str) -> str | None:
    """Return the verified email for a Google ID token, or None."""
    if not settings.google_client_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
    except httpx.HTTPError:
        log.exception("Google token check failed")
        return None
    if r.status_code != 200:
        return None
    info = r.json()
    if info.get("aud") != settings.google_client_id or info.get("email_verified") not in ("true", True):
        return None
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    return info.get("email")


# --- FastAPI dependencies -----------------------------------------------------

def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in or continue as a guest.")
    principal = read_token(authorization[7:].strip())
    if principal is None:
        raise HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    return principal


def require_member(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.is_guest:
        raise HTTPException(status_code=403, detail="Please sign in to use this.")
    return principal


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only.")
    return principal
