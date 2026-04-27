"""Configuration loader (YAML + .env)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT_DIR / ".env")


class Settings:
    """Runtime settings backed by environment variables and config.yaml."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or (ROOT_DIR / "config.yaml")
        with self.config_path.open("r", encoding="utf-8") as fp:
            self.sources: dict[str, Any] = yaml.safe_load(fp)

        # ---- secrets / env ----
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.email_from = os.getenv("EMAIL_FROM", self.smtp_username)
        self.email_to = os.getenv("EMAIL_TO", "")

        self.timezone = os.getenv("TIMEZONE", "Africa/Algiers")
        self.max_listings_per_source = int(os.getenv("MAX_LISTINGS_PER_SOURCE", "50"))
        self.top_opportunities_count = int(os.getenv("TOP_OPPORTUNITIES_COUNT", "10"))
        self.dry_run = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

        self.db_path = DATA_DIR / "souk_dz.db"

    # ------------------------------------------------------------------ helpers

    def source_config(self, key: str) -> dict[str, Any]:
        return self.sources.get(key, {}) or {}

    @property
    def opportunity_config(self) -> dict[str, Any]:
        return self.sources.get("opportunity", {}) or {}

    @property
    def categories_blacklist(self) -> list[str]:
        return self.sources.get("categories_blacklist", []) or []

    def has_email_credentials(self) -> bool:
        return all([self.smtp_username, self.smtp_password, self.email_to])

    def has_ai_credentials(self) -> bool:
        return bool(self.gemini_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
