"""
app/connectors/outlook/settings.py
===================================
OutlookSettings — Outlook-specific OAuth configuration.

Owns every environment variable required to authenticate against Microsoft
Azure AD.  Nothing here belongs in AppSettings — keeping connector settings
isolated follows the Single Responsibility Principle and prevents AppSettings
from becoming a god-object as new connectors are added.

WHAT THIS MODULE DOES
---------------------
  • Reads OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_REDIRECT_URI from
    the environment (or .env file).
  • Exposes computed URL properties (authority_url, authorize_url, token_url).
  • Exposes the OAuth scopes required by this connector.

WHAT THIS MODULE DOES NOT DO
------------------------------
  • It does NOT make any HTTP requests.
  • It does NOT create any API clients.
  • It does NOT contain any business logic.
  • It does NOT import from app.config.settings or any other app module.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • pydantic-settings

It must NOT import from app.config.settings or any other app module.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class OutlookSettings(BaseSettings):
    """
    Outlook / Azure AD configuration loaded from environment variables.

    Required variables (must be set in .env or environment):
      OUTLOOK_CLIENT_ID  — Azure app registration client ID
      OUTLOOK_TENANT_ID  — Azure AD directory (tenant) ID

    Optional variables (have sensible defaults):
      OUTLOOK_REDIRECT_URI — must match the redirect URI registered in Azure
    """

    # ------------------------------------------------------------------
    # Azure App Registration
    # ------------------------------------------------------------------
    outlook_client_id: str
    outlook_tenant_id: str
    outlook_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"

    # ------------------------------------------------------------------
    # Microsoft Identity Platform URLs
    # ------------------------------------------------------------------

    @property
    def authority_url(self) -> str:
        """
        Base URL for Microsoft OAuth 2.0 endpoints.

        All authorize and token requests are made to sub-paths of this URL.
        Format: https://login.microsoftonline.com/{tenant}/oauth2/v2.0
        """
        return (
            f"https://login.microsoftonline.com"
            f"/{self.outlook_tenant_id}/oauth2/v2.0"
        )

    @property
    def authorize_url(self) -> str:
        """Full URL for the authorization (login redirect) endpoint."""
        return f"{self.authority_url}/authorize"

    @property
    def token_url(self) -> str:
        """Full URL for the token exchange and refresh endpoint."""
        return f"{self.authority_url}/token"

    # ------------------------------------------------------------------
    # OAuth Scopes
    # ------------------------------------------------------------------

    @property
    def scopes(self) -> list[str]:
        """
        Delegated permission scopes requested during the OAuth flow.

        Scope breakdown:
          User.Read       — read the signed-in user's profile (/me)
          Calendars.Read  — read calendar events (used from Phase 4 onward)
          Mail.Read       — read email messages (used from Phase 5 onward)
          offline_access  — receive a refresh_token for silent token renewal

        All four are requested at login time so the user only needs to
        consent once.  Scopes for future phases are included now to avoid
        a second consent prompt when those phases ship.
        """
        return [
            "User.Read",
            "Calendars.Read",
            "Mail.Read",
            "offline_access",
        ]

    @property
    def scopes_str(self) -> str:
        """Space-separated scope string for OAuth query/body parameters."""
        return " ".join(self.scopes)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_outlook_settings() -> OutlookSettings:
    """
    Return a cached singleton OutlookSettings instance.

    lru_cache ensures the .env file is read only once per process lifetime.
    Call get_outlook_settings.cache_clear() in tests to reset between cases.
    """
    return OutlookSettings()
