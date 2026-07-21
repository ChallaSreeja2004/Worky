"""
app/connectors/slack/settings.py
==================================
SlackSettings — Slack-specific configuration loaded from .env.

Reads SLACK_BOT_TOKEN and SLACK_ALLOWED_CHANNEL_IDS from the environment.
The bot token is used directly by SlackAPIClient.  The allowed channel list,
when set, restricts which channels are fetched — only those IDs are included.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • pydantic-settings

It must NOT import from any other app module.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackSettings(BaseSettings):
    """
    Slack configuration loaded from environment variables.

    Required variables (must be set in .env or environment):
      SLACK_BOT_TOKEN            — bot user OAuth token (xoxb-...)

    Optional variables:
      SLACK_ALLOWED_CHANNEL_IDS  — comma-separated Slack channel IDs to fetch.
                                   When empty or unset, all accessible channels
                                   are fetched.
                                   Example: C012AB3CD,C999XYZ12

    Required Slack app scopes:
      channels:read    — list public channels
      groups:read      — list private channels the bot is a member of
      channels:history — read messages from public channels
      groups:history   — read messages from private channels
    """

    slack_bot_token: str

    # Stored as a raw string so pydantic-settings does not try to JSON-decode
    # it.  Use the .allowed_channel_ids property to get the parsed list.
    slack_allowed_channel_ids: str = ""

    @property
    def allowed_channel_ids(self) -> list[str]:
        """
        Parse SLACK_ALLOWED_CHANNEL_IDS into a list of channel ID strings.

        Splits on commas, strips whitespace, and drops empty entries.
        Returns an empty list when the value is unset — meaning all channels
        accessible to the bot are fetched.
        """
        return [ch.strip() for ch in self.slack_allowed_channel_ids.split(",") if ch.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_slack_settings() -> SlackSettings:
    """
    Return a cached singleton SlackSettings instance.

    lru_cache ensures the .env file is read only once per process lifetime.
    Call get_slack_settings.cache_clear() in tests to reset between cases.
    """
    return SlackSettings()
