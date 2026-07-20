"""
app/bob/settings.py
====================
BobSettings — IBM Bob CLI configuration.

Owns every environment variable required to invoke Bob Shell as a subprocess.
Nothing here belongs in AppSettings — keeping Bob settings isolated follows
the Single Responsibility Principle and ADR-015.

WHAT THIS MODULE DOES
---------------------
  • Reads BOB_EXECUTABLE, BOB_CHAT_MODE, and BOB_TIMEOUT_SECONDS from the
    environment (or .env file).

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
    IBM Bob CLI configuration loaded from environment variables.

    Optional variables (all have sensible defaults for BobCLIService):
      BOB_EXECUTABLE    — path or name of the bob CLI command
      BOB_CHAT_MODE     — Bob chat mode used for reasoning calls
      BOB_TIMEOUT_SECONDS — total seconds to wait for Bob to respond

    Legacy variables (kept for backward compatibility, unused by BobCLIService):
      BOB_API_URL — retained so existing .env files do not cause validation errors
      BOB_API_KEY — retained so existing .env files do not cause validation errors
    """

    # ------------------------------------------------------------------
    # Bob Shell CLI
    # ------------------------------------------------------------------
    bob_executable: str = "bob"
    """
    Path or name of the Bob Shell CLI command.

    Defaults to "bob", resolved via PATH.  Override to an absolute path
    if bob is not on the system PATH in your deployment environment.

    Example: /usr/local/bin/bob
    """

    bob_chat_mode: str = "ask"
    """
    Bob chat mode for reasoning calls.  "ask" is the read-only mode
    that does not modify files or run shell commands.

    Valid choices: ask | code | plan | advanced
    """

    bob_timeout_seconds: float = 120.0
    """
    Total seconds to wait for Bob Shell to complete a request.

    Bob generation for a full WorkContext typically takes 15–30 s.
    120 s is a safe ceiling for production.  Lower this if you want
    faster failure detection; raise it for very large contexts.
    """

    # ------------------------------------------------------------------
    # Legacy — kept so existing .env files remain valid
    # ------------------------------------------------------------------
    bob_api_url: str = ""
    bob_api_key: str = ""

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
