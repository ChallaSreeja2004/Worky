"""
app/bob/settings.py
====================
BobSettings — IBM Bob API configuration.

Owns every environment variable required to communicate with the IBM Bob
reasoning service.  Nothing here belongs in AppSettings — keeping Bob settings
isolated follows the Single Responsibility Principle and ADR-015, which
mandates that each integration defines its own settings class rather than
growing AppSettings into a god-object.

WHAT THIS MODULE DOES
---------------------
  • Reads BOB_API_URL and BOB_API_KEY from the environment (or .env file).
  • Exposes a computed timeout property.

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


class BobSettings(BaseSettings):
    """
    IBM Bob API configuration loaded from environment variables.

    Required variables (must be set in .env or environment for IBMBobService):
      BOB_API_URL — base URL of the IBM Bob REST API endpoint
      BOB_API_KEY — API key used to authenticate with IBM Bob

    Optional variables (have sensible defaults):
      BOB_TIMEOUT_SECONDS — per-request timeout when calling IBM Bob
    """

    # ------------------------------------------------------------------
    # IBM Bob API
    # ------------------------------------------------------------------
    bob_api_url: str = ""
    """
    Base URL of the IBM Bob reasoning service endpoint.

    Example: https://bob.example.ibm.com/api/v1
    Must NOT have a trailing slash.

    Defaults to empty string — IBMBobService will raise BobConfigError if
    an actual call is attempted without a real URL being set.
    """

    bob_api_key: str = ""
    """
    API key for authenticating with IBM Bob.  Never logged.

    Defaults to empty string — IBMBobService will raise BobConfigError if
    an actual call is attempted without a real key being set.
    """

    bob_timeout_seconds: float = 30.0
    """
    Per-request HTTP timeout (seconds) when calling the IBM Bob API.

    Bob's reasoning may take several seconds for complex contexts.  30 s
    is the default maximum to avoid hanging the scheduled pipeline.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The shared .env also contains AppSettings and connector variables.
        # Ignore anything not declared on this class.
        extra="ignore",
    )


@lru_cache
def get_bob_settings() -> BobSettings:
    """
    Return a cached singleton BobSettings instance.

    lru_cache ensures the .env file is read only once per process lifetime.
    Call get_bob_settings.cache_clear() in tests to reset between cases.
    """
    return BobSettings()
