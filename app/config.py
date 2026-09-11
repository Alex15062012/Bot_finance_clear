from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def _empty_str_to_none(value: Any) -> Any:
    if value == "" or value is None:
        return None
    return value


OptionalInt = Annotated[int | None, BeforeValidator(_empty_str_to_none)]


class Settings(BaseSettings):
    """Техническая конфигурация. Контент сценариев — в БД."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    app_env: str = "development"
    bot_display_name: str = "Про Финансы Ясно"
    bot_username: str = ""

    max_bot_token: str = ""
    max_api_base_url: str = "https://platform-api2.max.ru"
    # TLS: MAX использует сертификаты Минцифры — нужен certs/ca-bundle.pem
    max_ssl_verify: bool = True
    max_ca_bundle: str = ""

    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    channel_chat_id: OptionalInt = None
    channel_url: str = "https://max.ru/id773272640550_biz"

    materials_start_payload: str = "materials"

    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/webhook/max"

    log_level: str = "INFO"
    log_json: bool = False

    # Минимальная веб-админка
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_secret_key: str = "dev-secret-change-me"
    admin_enabled: bool = True
    # MAX user_id владельцев (через запятую) — для команды /admin в боте
    admin_platform_user_ids: str = ""
    admin_public_url: str = "http://localhost:8000/admin"

    @field_validator(
        "admin_username",
        "admin_password",
        "admin_secret_key",
        mode="before",
    )
    @classmethod
    def _strip_admin_secrets(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def materials_deeplink(self) -> str:
        username = self.bot_username.lstrip("@")
        payload = self.materials_start_payload
        return f"https://max.ru/{username}?start={payload}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Перечитать .env (после смены пароля без полного рестарта процесса)."""
    get_settings.cache_clear()
    return get_settings()
