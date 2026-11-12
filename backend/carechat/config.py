"""Settings, read from environment variables."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Read KEY=value lines from backend/.env into the environment.

    Values already set in the environment win. Quotes around a value are removed, and
    values may hold spaces or <>, so "CareChat <no-reply@example.com>" works with or
    without quotes. Skipped during tests so a local .env can't change them.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


if "pytest" not in sys.modules:
    _load_dotenv(Path(os.getenv("CARECHAT_ENV_FILE", Path(__file__).resolve().parents[1] / ".env")))


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(v.strip().lower() for v in os.getenv(name, default).split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    # --- Claude ---
    # Model that writes answers and summaries and reads uploaded reports.
    answer_model: str = field(default_factory=lambda: os.getenv("CARECHAT_ANSWER_MODEL", "claude-sonnet-5-5"))
    # Fast model that checks every message for emergency signs.
    safety_model: str = field(default_factory=lambda: os.getenv("CARECHAT_SAFETY_MODEL", "claude-haiku-5-5"))
    # Server-side refusal fallbacks (Claude API only).
    use_fallbacks: bool = field(default_factory=lambda: _bool("CARECHAT_USE_FALLBACKS", True))
    # Claude stops being called once estimated spend this month passes this (USD). 0 = no cap.
    monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("CARECHAT_MONTHLY_BUDGET_USD", "25")))

    # --- Region and languages ---
    # Launch region: sets emergency numbers and messages. "IN" (India) or "US".
    region_code: str = field(default_factory=lambda: os.getenv("CARECHAT_REGION", "IN"))

    # --- Storage ---
    # "sqlite" for local development and tests, "catalyst" for Zoho Catalyst Data Store.
    store_backend: str = field(default_factory=lambda: os.getenv("CARECHAT_STORE", "sqlite"))
    db_path: str = field(default_factory=lambda: os.getenv("CARECHAT_DB_PATH", "carechat.db"))
    # Read-only knowledge base file (MedlinePlus and Indian public pages), shipped with the app.
    knowledge_path: str = field(default_factory=lambda: os.getenv("CARECHAT_KNOWLEDGE_PATH", "knowledge.db"))
    # Catalyst Data Store table that holds every record (see README).
    catalyst_table: str = field(default_factory=lambda: os.getenv("CARECHAT_CATALYST_TABLE", "records"))
    # Key for encrypting health data before it is saved (Fernet key, see README).
    encryption_key: str = field(default_factory=lambda: os.getenv("CARECHAT_ENCRYPTION_KEY", ""))

    # --- Sign-in ---
    # "dev" shows a no-password sign-in for local testing. Never use it in production.
    auth_mode: str = field(default_factory=lambda: os.getenv("CARECHAT_AUTH_MODE", "prod"))
    # Signs session tokens. Must be a long random string in production.
    secret_key: str = field(default_factory=lambda: os.getenv("CARECHAT_SECRET_KEY", ""))
    session_days: int = field(default_factory=lambda: int(os.getenv("CARECHAT_SESSION_DAYS", "30")))
    # Google sign-in OAuth client id (from Google Cloud console). Empty hides the Google button.
    google_client_id: str = field(default_factory=lambda: os.getenv("CARECHAT_GOOGLE_CLIENT_ID", ""))
    # Emails that get the Admin level when they sign in.
    admin_emails: tuple[str, ...] = field(default_factory=lambda: _list("CARECHAT_ADMIN_EMAILS"))

    # --- Email (sign-in codes and reminders) ---
    # "console" logs emails (development), "smtp" sends through an SMTP server.
    mail_backend: str = field(default_factory=lambda: os.getenv("CARECHAT_MAIL", "console"))
    smtp_host: str = field(default_factory=lambda: os.getenv("CARECHAT_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("CARECHAT_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("CARECHAT_SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("CARECHAT_SMTP_PASSWORD", ""))
    mail_from: str = field(default_factory=lambda: os.getenv("CARECHAT_MAIL_FROM", "CareChat <no-reply@example.com>"))
    app_url: str = field(default_factory=lambda: os.getenv("CARECHAT_APP_URL", "http://localhost:3000"))

    # --- SMS (mobile number sign-in) ---
    # "console" logs codes (development), "messagecentral" sends real SMS, "off" hides mobile sign-in.
    sms_backend: str = field(default_factory=lambda: os.getenv("CARECHAT_SMS", "console"))
    mc_customer_id: str = field(default_factory=lambda: os.getenv("CARECHAT_MC_CUSTOMER_ID", ""))
    mc_password: str = field(default_factory=lambda: os.getenv("CARECHAT_MC_PASSWORD", ""))
    # Every SMS costs money: a ceiling on codes sent per day across everyone.
    daily_sms_cap: int = field(default_factory=lambda: int(os.getenv("CARECHAT_DAILY_SMS_CAP", "100")))

    # --- Scheduled jobs ---
    # Shared secret the Catalyst cron sends in the X-Cron-Token header.
    cron_token: str = field(default_factory=lambda: os.getenv("CARECHAT_CRON_TOKEN", ""))
    # Also run the hourly jobs inside the server (handy locally; Catalyst cron is the main trigger).
    run_inprocess_jobs: bool = field(default_factory=lambda: _bool("CARECHAT_INPROCESS_JOBS", True))

    # --- Limits ---
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("CARECHAT_MAX_UPLOAD_MB", "10")) * 1024 * 1024)
    # Records without saved history are deleted after this many hours.
    report_retention_hours: float = field(default_factory=lambda: float(os.getenv("CARECHAT_REPORT_RETENTION_HOURS", "24")))
    daily_reports_per_user: int = field(default_factory=lambda: int(os.getenv("CARECHAT_DAILY_REPORTS", "10")))
    daily_questions_per_user: int = field(default_factory=lambda: int(os.getenv("CARECHAT_DAILY_QUESTIONS", "60")))

    # --- Token budget controls ---
    max_history_messages: int = 12  # last 6 exchanges
    max_assistant_chars_in_history: int = 2000  # long past answers are trimmed when resent
    max_sources: int = 3
    # Kept low so a streamed answer finishes well inside AppSail's 30-second request limit.
    answer_max_tokens: int = field(default_factory=lambda: int(os.getenv("CARECHAT_ANSWER_MAX_TOKENS", "1200")))
    summary_max_tokens: int = 2500
    extract_max_tokens: int = 8000
    max_message_chars: int = 4000

    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv("CARECHAT_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        )
    )

    @property
    def dev_auth(self) -> bool:
        return self.auth_mode == "dev"


settings = Settings()
