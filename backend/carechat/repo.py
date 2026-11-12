"""Reading and writing CareChat's records: accounts, profiles, consents, reports,
chat history, reminders, feedback and the audit log.

Retention rules live here:
- Guests: everything is deleted after 24 hours.
- Signed-in users without history: reports and chat are deleted after 24
  hours; profiles and the health form stay until deleted.
- With history on: kept until the user deletes them or withdraws consent.
- Consent records and the audit log are kept for proof, with no health data.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .store import CachedStore, Record, expiry, iso, now

NOTICE_VERSION = "2026-10-v1"

CONSENT_PURPOSES = ("processing", "history", "family", "terms", "adult")


def email_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class Repo:
    def __init__(self, store: CachedStore) -> None:
        self.store = store

    # --- accounts --------------------------------------------------------------
    def create_guest(self, language: str | None) -> Record:
        rec = Record(collection="account", data={"guest": True, "role": "guest", "ui_language": language or "en",
                                                 "history_enabled": False})
        rec.account_id = rec.id
        rec.expires_at = expiry(settings.report_retention_hours)
        return self.store.insert(rec)

    def account(self, account_id: str) -> Record | None:
        return self.store.get("account", account_id)

    def account_by_email(self, email: str) -> Record | None:
        found = self.store.find("account", ref_id=email_key(email))
        return found[0] if found else None

    def get_or_create_member(self, email: str, role: str, name: str | None = None, language: str | None = None) -> Record:
        rec = self.account_by_email(email)
        if rec is not None:
            if rec.data.get("role") != role:
                rec.data["role"] = role
                self.store.update(rec)
            return rec
        rec = Record(collection="account", ref_id=email_key(email), data={
            "guest": False, "role": role, "email": email.strip().lower(), "name": name or "",
            "ui_language": language or "en", "history_enabled": False, "reminder_emails": True,
        })
        rec.account_id = rec.id
        return self.store.insert(rec)

    def update_account(self, rec: Record) -> Record:
        return self.store.update(rec)

    def claim_guest(self, guest_id: str, member: Record) -> int:
        """Move a guest's profiles and reports into the account they just signed in to."""
        moved = 0
        keep = member.data.get("history_enabled", False)
        for collection in ("profile", "report", "message"):
            for rec in self.store.find(collection, account_id=guest_id):
                rec.account_id = member.id
                if collection == "profile":
                    rec.expires_at = None
                    rec.data["is_self"] = rec.data.get("is_self") and not self._has_self(member.id)
                elif keep:
                    rec.expires_at = None
                self.store.update(rec)
                moved += 1
        for rec in self.store.find("consent", ref_id=guest_id):
            rec.ref_id = member.id
            self.store.update(rec)
        self.store.delete("account", guest_id)
        return moved

    def _has_self(self, account_id: str) -> bool:
        return any(p.data.get("is_self") for p in self.store.find("profile", account_id=account_id))

    def retention_for(self, account: Record) -> str | None:
        """Expiry for new reports and chat for this account."""
        if account.data.get("guest") or not account.data.get("history_enabled"):
            return expiry(settings.report_retention_hours)
        return None

    def set_history(self, account: Record, enabled: bool) -> Record:
        account.data["history_enabled"] = enabled
        self.store.update(account)
        for collection in ("report", "message"):
            for rec in self.store.find(collection, account_id=account.id):
                if enabled and rec.expires_at is not None:
                    rec.expires_at = None
                    self.store.update(rec)
                elif not enabled:
                    self.store.delete(collection, rec.id)
        return account

    def delete_account(self, account_id: str) -> int:
        """Delete everything the account owns. Consent records and the audit log stay, with no health data."""
        n = self.store.delete_where(account_id=account_id)
        return n

    # --- profiles ---------------------------------------------------------------
    def profiles(self, account_id: str) -> list[Record]:
        return self.store.find("profile", account_id=account_id)

    def profile(self, account_id: str, profile_id: str) -> Record | None:
        rec = self.store.get("profile", profile_id)
        # The single ownership check every profile read and write goes through.
        if rec is None or rec.account_id != account_id:
            return None
        return rec

    def create_profile(self, account: Record, data: dict[str, Any]) -> Record:
        rec = Record(collection="profile", account_id=account.id, data=data)
        rec.profile_id = rec.id
        if account.data.get("guest"):
            rec.expires_at = account.expires_at
        return self.store.insert(rec)

    def save_profile(self, rec: Record) -> Record:
        return self.store.update(rec)

    def delete_profile(self, account_id: str, profile_id: str) -> int:
        n = 0
        for collection in ("report", "message", "reminder"):
            for rec in self.store.find(collection, account_id=account_id, profile_id=profile_id):
                n += self.store.delete(collection, rec.id)
        n += self.store.delete("profile", profile_id)
        return n

    # --- consent ----------------------------------------------------------------
    def record_consent(self, account_id: str, purpose: str, granted: bool, language: str | None,
                       profile_id: str | None = None) -> Record:
        rec = Record(collection="consent", ref_id=account_id, profile_id=profile_id, data={
            "purpose": purpose, "granted": granted, "notice_version": NOTICE_VERSION, "language": language or "en",
            "at": iso(now()),
        })
        return self.store.insert(rec)

    def consents(self, account_id: str) -> dict[str, bool]:
        state: dict[str, bool] = {}
        for rec in self.store.find("consent", ref_id=account_id):
            if rec.profile_id:
                continue
            if rec.data.get("notice_version") == NOTICE_VERSION:
                state[rec.data["purpose"]] = rec.data["granted"]
        return state

    def has_processing_consent(self, account_id: str) -> bool:
        c = self.consents(account_id)
        return bool(c.get("processing") and c.get("terms") and c.get("adult"))

    # --- reports ----------------------------------------------------------------
    def create_report(self, account: Record, profile_id: str, data: dict[str, Any]) -> Record:
        rec = Record(collection="report", account_id=account.id, profile_id=profile_id, data=data,
                     expires_at=self.retention_for(account))
        return self.store.insert(rec)

    def report(self, account_id: str, report_id: str) -> Record | None:
        rec = self.store.get("report", report_id)
        if rec is None or rec.account_id != account_id:
            return None
        return rec

    def reports(self, account_id: str, profile_id: str | None = None) -> list[Record]:
        if profile_id:
            return self.store.find("report", account_id=account_id, profile_id=profile_id)
        return self.store.find("report", account_id=account_id)

    def save_report(self, rec: Record) -> Record:
        return self.store.update(rec)

    def delete_report(self, account_id: str, report_id: str) -> bool:
        rec = self.report(account_id, report_id)
        if rec is None:
            return False
        for msg in self.store.find("message", account_id=account_id, ref_id=report_id):
            self.store.delete("message", msg.id)
        return self.store.delete("report", report_id)

    # --- chat history -----------------------------------------------------------
    def save_exchange(self, account: Record, profile_id: str | None, report_id: str | None,
                      question: str, answer: str) -> Record | None:
        if account.data.get("guest") or not account.data.get("history_enabled"):
            return None  # without history, the conversation lives only in the browser
        rec = Record(collection="message", account_id=account.id, profile_id=profile_id, ref_id=report_id or "general",
                     data={"question": question, "answer": answer, "at": iso(now())})
        return self.store.insert(rec)

    def exchanges(self, account_id: str, report_id: str) -> list[Record]:
        return self.store.find("message", account_id=account_id, ref_id=report_id)

    # --- reminders --------------------------------------------------------------
    def reminders(self, account_id: str) -> list[Record]:
        return self.store.find("reminder", account_id=account_id)

    def all_reminders(self) -> list[Record]:
        return self.store.find_since("reminder", "0")

    def create_reminder(self, account: Record, profile_id: str | None, data: dict[str, Any]) -> Record:
        rec = Record(collection="reminder", account_id=account.id, profile_id=profile_id, data=data)
        return self.store.insert(rec)

    def delete_reminder(self, account_id: str, reminder_id: str) -> bool:
        rec = self.store.get("reminder", reminder_id)
        if rec is None or rec.account_id != account_id:
            return False
        return self.store.delete("reminder", reminder_id)

    # --- feedback and audit -----------------------------------------------------
    def add_feedback(self, data: dict[str, Any]) -> Record:
        # Not linked to the account: reviewers see the redacted question and answer only.
        rec = Record(collection="feedback", data={**data, "at": iso(now())}, expires_at=expiry(24 * 90))
        return self.store.insert(rec)

    def feedback_since(self, since: str) -> list[Record]:
        return self.store.find_since("feedback", since)

    def audit(self, actor_id: str, actor_role: str, action: str, target: str = "") -> Record:
        rec = Record(collection="audit", ref_id=actor_id, data={
            "actor_role": actor_role, "action": action, "target": target, "at": iso(now()),
        })
        return self.store.insert(rec)

    def audit_since(self, since: str) -> list[Record]:
        return self.store.find_since("audit", since)

    def consents_since(self, since: str) -> list[Record]:
        return self.store.find_since("consent", since)

    # --- metrics ----------------------------------------------------------------
    def save_metrics(self, snapshot: dict[str, Any]) -> Record:
        return self.store.insert(Record(collection="metrics", data=snapshot, expires_at=expiry(24 * 400)))

    def metrics_since(self, since: str) -> list[dict[str, Any]]:
        return [r.data for r in self.store.find_since("metrics", since)]


def age_from_birth_year(birth_year: int | None) -> int | None:
    if not birth_year:
        return None
    return datetime.now(timezone.utc).year - int(birth_year)
