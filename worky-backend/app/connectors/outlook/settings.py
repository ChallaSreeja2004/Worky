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
  • Reads OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_REDIRECT_URI,
    and OUTLOOK_CLIENT_SECRET from the environment (or .env file).
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

import logging
import re
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger(__name__)

# A bare UUID4 pattern (32 hex digits with hyphens).  When OUTLOOK_TENANT_ID
# is set to a specific Azure AD tenant GUID, personal Microsoft Accounts
# (MSA, e.g. Gmail/Hotmail addresses used as MS accounts) will authenticate
# successfully but receive access tokens that Microsoft Graph rejects with
# HTTP 401 because the token's "tid" claim (9188040d-…) does not match the
# registered app tenant.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class OutlookSettings(BaseSettings):
    """
    Outlook / Azure AD configuration loaded from environment variables.

    Required variables (must be set in .env or environment):
      OUTLOOK_CLIENT_ID      — Azure app registration client ID
      OUTLOOK_TENANT_ID      — Azure AD directory (tenant) ID
      OUTLOOK_CLIENT_SECRET  — Azure app registration client secret
                               (required for confidential-client token exchange)

    Optional variables (have sensible defaults):
      OUTLOOK_REDIRECT_URI   — must match the redirect URI registered in Azure
    """

    # ------------------------------------------------------------------
    # Azure App Registration
    # ------------------------------------------------------------------
    outlook_client_id: str
    outlook_tenant_id: str
    outlook_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"

    # Client secret for confidential-client OAuth 2.0 token requests.
    # Azure AD requires either client_secret or client_assertion in every
    # token request for app registrations with a "Web" redirect URI type.
    # Set via OUTLOOK_CLIENT_SECRET in .env.
    outlook_client_secret: str = ""

    @model_validator(mode="after")
    def _require_client_secret(self) -> "OutlookSettings":
        """
        Fail at startup with a clear message when the client secret is absent.

        Without this guard, the missing secret produces an opaque
        AADSTS7000218 error from Microsoft's token endpoint only after
        the user completes the login redirect — far harder to diagnose.
        """
        if not self.outlook_client_secret:
            raise ValueError(
                "OUTLOOK_CLIENT_SECRET is not set. "
                "Add it to your .env file. "
                "Find it in Azure Portal → App registrations → "
                "your app → Certificates & secrets → Client secrets."
            )

        # Warn when a specific Azure AD tenant GUID is used.
        # Personal Microsoft Accounts (MSA) authenticate successfully at
        # tenant-specific endpoints but receive access tokens with
        # tid=9188040d-6c67-4c5b-b112-36a304b66dad (the MSA pseudo-tenant).
        # Microsoft Graph rejects those tokens with HTTP 401 because the
        # app was registered in a different tenant.
        # Fix: set OUTLOOK_TENANT_ID=consumers (personal only) or
        # OUTLOOK_TENANT_ID=common (personal + work/school) in .env.
        if _UUID_RE.match(self.outlook_tenant_id):
            _log.warning(
                "OutlookSettings: OUTLOOK_TENANT_ID is a specific Azure AD "
                "tenant GUID (%s).  Personal Microsoft Accounts (MSA) will "
                "receive access tokens that Microsoft Graph rejects with "
                "HTTP 401.  If you are using a personal account "
                "(Outlook.com / Hotmail / Gmail-based MSA), change "
                "OUTLOOK_TENANT_ID to 'consumers' or 'common' in your .env.",
                self.outlook_tenant_id,
            )

        return self

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
          openid          — required for OpenID Connect; Microsoft returns an
                            id_token in the token response only when this scope
                            is present (OIDC core)
          profile         — includes name, oid, and preferred_username claims
                            in the id_token
          email           — includes email claim in the id_token
          User.Read       — read the signed-in user's profile via Graph /me
                            (also serves as the Graph API identity fallback)
          Calendars.Read  — read calendar events (used from Phase 4 onward)
          Mail.Read       — read email messages (used from Phase 5 onward)
          offline_access  — receive a refresh_token for silent token renewal

        All scopes are requested at login time so the user only needs to
        consent once.  Scopes for future phases are included now to avoid
        a second consent prompt when those phases ship.

        The three OIDC scopes (openid, profile, email) are placed first so
        that Microsoft's scope validation sees them before the Graph scopes.
        """
        return [
            "openid",
            "profile",
            "email",
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
        # The shared .env also contains AppSettings variables (TOKEN_ENCRYPTION_KEY,
        # LOG_LEVEL, etc.) and future connector variables.  Ignore anything that is
        # not declared on this class so pydantic-settings does not raise on them.
        extra="ignore",
    )


@lru_cache
def get_outlook_settings() -> OutlookSettings:
    """
    Return a cached singleton OutlookSettings instance.

    lru_cache ensures the .env file is read only once per process lifetime.
    Call get_outlook_settings.cache_clear() in tests to reset between cases.
    """
    return OutlookSettings()
