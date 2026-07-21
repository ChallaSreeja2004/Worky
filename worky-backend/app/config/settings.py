"""
app/config/settings.py
======================
Global application settings loaded from environment variables.

This module owns ONLY application-level concerns:
  • Runtime environment (development / production)
  • Logging level
  • Token encryption key (shared across all connectors)
  • API versioning prefix
  • Frontend URL — optional redirect target after OAuth callback

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

    # ------------------------------------------------------------------
    # Connector mode
    # ------------------------------------------------------------------
    connector_mode: Literal["outlook", "demo"] = "outlook"
    """
    Controls which Outlook data source is used throughout the pipeline.

    "outlook"  (default)
        Full production path: Microsoft OAuth → GraphAPIClient →
        OutlookConnector → real calendar and email data.

    "demo"
        No Microsoft credentials required.  DemoOutlookConnector returns
        realistic synthetic data.  The entire authentication and Graph API
        layer is bypassed.

    Changing this single variable is the ONLY configuration change needed
    to switch between production and demo execution.
    """

    # ------------------------------------------------------------------
    # Frontend — optional redirect target after OAuth callback
    # ------------------------------------------------------------------
    frontend_url: str | None = None
    """
    Base URL of the React / desktop widget frontend.

    When set, the OAuth callback endpoint redirects the browser to
        {frontend_url}/auth/success?user_id=...&display_name=...&email=...
    instead of returning the AuthorizationResponse as JSON.

    When not set (the default), the callback returns JSON exactly as
    before — preserving full backward compatibility for API clients,
    automated tests, and curl-based development workflows.

    Set this to the Vite dev server origin during frontend development:
        FRONTEND_URL=http://localhost:3000

    Must NOT have a trailing slash.
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
