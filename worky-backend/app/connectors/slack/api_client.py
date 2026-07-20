"""
app/connectors/slack/api_client.py
====================================
SlackAPIClient — async HTTP abstraction for Slack Web API calls.

RESPONSIBILITIES
----------------
  • Wrap slack_sdk.web.async_client.AsyncWebClient with a clean, typed interface.
  • Attach the bot token (loaded from SlackSettings) on every request.
  • Return raw Slack API response dicts — no normalisation, no transformation.
  • Raise typed, Slack-specific exceptions so callers can react precisely.

WHAT THIS CLIENT DOES NOT DO
------------------------------
  • It does NOT refresh tokens — the bot token is long-lived and static.
  • It does NOT normalise or interpret Slack responses.
  • It does NOT contain business logic.
  • It does NOT import from any other app module except slack/settings.py.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • slack_sdk
  • app.connectors.slack.settings

It must NOT import from:
  • app.auth
  • app.config
  • app.connectors.base
  • app.connectors.models
  • app.context_builder
"""

from __future__ import annotations

import logging
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SlackAPIClient
# ---------------------------------------------------------------------------

class SlackAPIClient:
    """
    Authenticated, async client for the Slack Web API.

    Wraps AsyncWebClient and exposes only the methods required by the
    Slack connector fetchers.  Constructed once per connector execution
    cycle using the bot token from SlackSettings.

    Parameters
    ----------
    bot_token : str
        A valid Slack bot user OAuth token (xoxb-...).
        Obtain from https://api.slack.com/apps → OAuth & Permissions.
    """

    def __init__(self, bot_token: str) -> None:
        self._client = AsyncWebClient(token=bot_token)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_channels(self) -> list[dict[str, Any]]:
        """
        Fetch all channels the bot can access.

        Slack API method: conversations.list
        Required scopes: channels:read, groups:read

        Parameters
        ----------
        None — uses the bot token provided at construction time.

        Returns
        -------
        list[dict[str, Any]]
            Raw Slack channel objects.  Each dict contains at minimum:
            ``id``, ``name``, ``is_private``.

        Raises
        ------
        SlackClientError
            On any Slack API error (invalid token, missing scope, etc.).
        """
        try:
            response = await self._client.conversations_list(
                types="public_channel,private_channel",
            )
            channels: list[dict[str, Any]] = response.get("channels") or []
            logger.debug("SlackAPIClient.get_channels: received %d channel(s)", len(channels))
            return channels
        except SlackApiError as exc:
            error_code = exc.response.get("error", "unknown_error")
            logger.error("SlackAPIClient.get_channels failed: %s", error_code)
            raise SlackClientError(f"conversations.list failed: {error_code}") from exc

    async def get_messages(self, channel_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Fetch the latest messages from a single channel.

        Slack API method: conversations.history
        Required scopes: channels:history, groups:history

        Parameters
        ----------
        channel_id : str
            Slack channel ID (e.g. "C012AB3CD").
        limit : int
            Maximum number of messages to retrieve.  Defaults to 20.

        Returns
        -------
        list[dict[str, Any]]
            Raw Slack message objects.  Each dict contains at minimum:
            ``user``, ``text``, ``ts``.

        Raises
        ------
        SlackClientError
            On any Slack API error (channel not found, missing scope, etc.).
        """
        try:
            response = await self._client.conversations_history(
                channel=channel_id,
                limit=limit,
            )
            messages: list[dict[str, Any]] = response.get("messages") or []
            logger.debug(
                "SlackAPIClient.get_messages: channel=%s received %d message(s)",
                channel_id, len(messages),
            )
            return messages
        except SlackApiError as exc:
            error_code = exc.response.get("error", "unknown_error")
            logger.error(
                "SlackAPIClient.get_messages failed: channel=%s error=%s",
                channel_id, error_code,
            )
            raise SlackClientError(
                f"conversations.history failed for channel {channel_id!r}: {error_code}"
            ) from exc

    async def ping(self) -> bool:
        """
        Verify that the Slack API is reachable and the token is valid.

        Calls auth.test and returns True on success.  Returns False on any
        failure without raising — used by SlackConnector.health_check().

        Returns
        -------
        bool
            True  — Slack API responded successfully.
            False — Any error occurred (network, invalid token, …).
        """
        try:
            await self._client.auth_test()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SlackAPIClient.ping: health check failed — %s", exc)
            return False


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class SlackClientError(Exception):
    """
    Raised by SlackAPIClient when the Slack Web API returns an error.

    Wraps SlackApiError with a plain string message so callers do not need
    to import slack_sdk.errors directly.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
