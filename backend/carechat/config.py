"""Settings, read from environment variables."""

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Model that writes answers and reads uploaded reports.
    answer_model: str = field(default_factory=lambda: os.getenv("CARECHAT_ANSWER_MODEL", "claude-sonnet-5-5"))
    # Fast model that checks every message for emergency signs.
    safety_model: str = field(default_factory=lambda: os.getenv("CARECHAT_SAFETY_MODEL", "claude-haiku-5-5"))
    # Server-side refusal fallbacks (Claude API only; turn off on Bedrock/Vertex).
    use_fallbacks: bool = field(default_factory=lambda: _bool("CARECHAT_USE_FALLBACKS", True))
    # Launch region: sets emergency numbers and messages. "IN" (India) or "US".
    region_code: str = field(default_factory=lambda: os.getenv("CARECHAT_REGION", "IN"))
    db_path: str = field(default_factory=lambda: os.getenv("CARECHAT_DB_PATH", "carechat.db"))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("CARECHAT_MAX_UPLOAD_MB", "10")) * 1024 * 1024)
    max_history_messages: int = 20
    max_message_chars: int = 4000
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv("CARECHAT_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        )
    )


settings = Settings()
