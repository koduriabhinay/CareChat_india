"""Hourly jobs, run by the Catalyst cron (and inside the server as a backup).

- Delete expired records (no-history reports and chat, guest accounts).
- Save the hour's usage metrics.
- Email reminders that fall in this hour.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .config import settings
from .mailer import send_email
from .metrics import metrics
from .repo import Repo

log = logging.getLogger(__name__)

# Reminder times are entered in India time.
IST = timezone(timedelta(hours=5, minutes=30))


def due_this_hour(schedule: dict, at: datetime) -> bool:
    """Is a reminder due in the hour that contains `at` (India time)? Computed, so nothing is written."""
    local = at.astimezone(IST)
    time_text = schedule.get("time") or "09:00"
    try:
        hour = int(time_text.split(":")[0])
    except ValueError:
        return False
    if hour != local.hour:
        return False
    kind = schedule.get("type", "daily")
    if kind == "daily":
        return True
    if kind == "once":
        return schedule.get("date") == local.strftime("%Y-%m-%d")
    if kind == "monthly":
        return str(schedule.get("day", "")) == str(local.day)
    return False


_last_reminder_hour: str | None = None


async def send_due_reminders(repo: Repo, at: datetime | None = None) -> int:
    global _last_reminder_hour
    at = at or datetime.now(timezone.utc)
    hour_key = at.strftime("%Y-%m-%dT%H")
    if hour_key == _last_reminder_hour:
        return 0  # already sent this hour (cron and the in-server timer can both fire)
    _last_reminder_hour = hour_key
    sent = 0
    for rem in repo.all_reminders():
        data = rem.data
        if not data.get("active", True) or not data.get("email"):
            continue
        if not due_this_hour(data.get("schedule", {}), at):
            continue
        account = repo.account(rem.account_id or "")
        if account is None or not account.data.get("email") or not account.data.get("reminder_emails", True):
            continue
        body = (
            f"Reminder from CareChat: {data.get('title', '')}\n\n"
            "You set this reminder yourself in CareChat. CareChat never suggests medicines or doses; "
            "follow your doctor's advice.\n\n"
            f"Manage your reminders: {settings.app_url}/reminders"
        )
        if await send_email(account.data["email"], f"Reminder: {data.get('title', '')}", body):
            sent += 1
    if sent:
        metrics.event("reminder_emails", sent)
    return sent


async def run_hourly(repo: Repo) -> dict:
    result = {"purged": 0, "metrics_saved": False, "reminders": 0}
    try:
        result["purged"] = repo.store.purge_expired()
    except Exception:
        log.exception("Purge failed")
        metrics.event("job_errors")
    try:
        snap = metrics.roll()
        if snap:
            repo.save_metrics(snap)
            result["metrics_saved"] = True
    except Exception:
        log.exception("Saving metrics failed")
    try:
        result["reminders"] = await send_due_reminders(repo)
    except Exception:
        log.exception("Reminders failed")
        metrics.event("job_errors")
    log.info("hourly purged=%s metrics_saved=%s reminders=%s", result["purged"], result["metrics_saved"], result["reminders"])
    return result
