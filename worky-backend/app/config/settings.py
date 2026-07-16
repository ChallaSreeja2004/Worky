"""
app/config/settings.py
======================
Global application settings loaded from environment variables.

This module owns ONLY application-level concerns:
  • Runtime environment (development / production)
  • Logging level
  • Token encryption key (shared across all connectors)
  • API versioning prefix

Connector-specific settings (OAuth scopes, API base URLs, client IDs) live in
each connector's own settings module, e.g.
  app/connectors/outlook/settings.py
  app/connectors/slack/settings.py

This separation follows the Single Responsibility Principle and prevents this
class from becoming a god-object as new connectors are added by teammates.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    Application-level configuration.

    All values are read from environment variables (case-insensitive) or
    from a .env file in the project root.  No connector-specific values
    belong here.
    """

    # ------------------------------------------------------------------
    # Application identity
    # ------------------------------------------------------------------
    app_name: str = "worky-backend"
    app_port: int = 8000

    # ------------------------------------------------------------------
    # Runtime environment
    # ------------------------------------------------------------------
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    api_v1_prefix: str = "/api/v1"
    """
    All routes are mounted under this prefix.
    Versioning from day one avoids a painful migration when the desktop
    widget v1 and a backend v2 must coexist in the field.
    """

    # ------------------------------------------------------------------
    # Security — token encryption
    # ------------------------------------------------------------------
    token_encryption_key: str
    """
    Fernet symmetric encryption key used to encrypt refresh tokens before
    they are persisted by any TokenRepository implementation.

    Generate a key with:
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    This key is shared across all connectors because the AuthService is a
    shared layer — each connector does not manage its own encryption.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Connector-specific variables (OUTLOOK_*, SLACK_*, etc.) live in each
        # connector's own settings class.  Ignore them here so AppSettings does
        # not raise ValidationError when the shared .env contains those keys.
        extra="ignore",
    )


@lru_cache
def get_settings() -> AppSettings:
    """
    Return a cached singleton AppSettings instance.

    Using lru_cache ensures the .env file is read only once per process
    lifetime, even if get_settings() is called from many modules.
    """
    return AppSettings()
