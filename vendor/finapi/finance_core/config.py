"""Environment configuration shared by the API and the Telegram bot.

Both entrypoints read the same database path, timezone, currency, and
environment from here so the two processes cannot drift apart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class CommonSettings:
    """Configuration values every adapter needs."""

    database_path: str = "bot04.sqlite3"
    timezone: str = "Asia/Jakarta"
    currency: str = "IDR"
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


def env_value(name: str, default: str) -> str:
    """Read and normalize one environment value."""

    return os.getenv(name, default).strip()


@lru_cache(maxsize=1)
def _load_dotenv_once() -> None:
    load_dotenv()


def get_common_settings(*, load_dotenv_file: bool = True) -> CommonSettings:
    """Read shared settings from the environment."""

    if load_dotenv_file:
        _load_dotenv_once()

    return CommonSettings(
        database_path=env_value("DATABASE_PATH", "bot04.sqlite3"),
        timezone=env_value("TIMEZONE", "Asia/Jakarta"),
        currency=env_value("CURRENCY", "IDR"),
        environment=env_value("ENVIRONMENT", "development"),
    )