"""
app/connectors/slack/connector.py
===================================
SlackConnector — BaseConnector implementation for Slack.

RESPONSIBILITIES
----------------
  • Implement the BaseConnector interface for the Slack enterprise application.
  • Accept a pre-built SlackAPIClient and SlackNormalizer via constructor injection.
  • Call self._client.get_channels() then self._client.get_messages() per channel.
  • Run per-channel message fetches concurrently via asyncio.gather().
  • Normalize both payloads into a SlackContext via SlackNormalizer.
  • Return ConnectorResult.success() when both fetches succeed.
  • Return ConnectorResult.partial() when message fetch fails but channels succeed.
  • Return ConnectorResult.failed() when channels fetch fails entirely.
  • Implement health_check() via SlackAPIClient.ping() — never raises.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT read SLACK_BOT_TOKEN — callers construct the SlackAPIClient.
  • It does NOT call IBM Bob.
  • It does NOT know about ContextBuilder or WorkContext.
  • It does NOT import from app.auth.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.base
  • app.connectors.models
  • app.connectors.slack.api_client
  • app.connectors.slack.normalizer
  • app.connectors.slack.models
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
from app.connectors.slack.api_client import SlackAPIClient, SlackClientError
from app.connectors.slack.normalizer import SlackNormalizer

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    """
    Collects channel list and latest messages from Slack and returns a
    normalised ConnectorResult.

    Parameters
    ----------
    api_client : SlackAPIClient
        An authenticated Slack API client constructed with a valid bot token.

    normalizer : SlackNormalizer
        The normalizer used to convert raw Slack dicts into SlackContext.
        Injected so it can be replaced with a test double.

    allowed_channel_ids : list[str] | None
        When provided (and non-empty), only channels whose ID is in this list
        are fetched.  Populated from SLACK_ALLOWED_CHANNEL_IDS in .env.
        Pass an empty list or None to fetch all accessible channels.

    Example
    -------
    ::

        client = SlackAPIClient(bot_token="xoxb-...")
        connector = SlackConnector(api_client=client, normalizer=SlackNormalizer())
        result = await connector.get_context()
    """

    def __init__(
        self,
        api_client: SlackAPIClient,
        normalizer: SlackNormalizer,
        allowed_channel_ids: list[str] | None = None,
    ) -> None:
        self._client = api_client
        self._normalizer = normalizer
        self._allowed: frozenset[str] = frozenset(allowed_channel_ids or [])

    # ------------------------------------------------------------------
    # BaseConnector — identity
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return "slack"

    # ------------------------------------------------------------------
    # BaseConnector — core contract
    # ------------------------------------------------------------------

    async def get_context(self) -> ConnectorResult:
        """
        Fetch Slack channels and latest messages, then normalise and return.

        Channels are fetched first.  If that succeeds, messages are fetched
        for all channels concurrently.  If messages fail, a PARTIAL result is
        returned with the channel list intact.  If channels fail, FAILED.

        Returns
        -------
        ConnectorResult
            ConnectorResult.success()  — both fetches succeeded.
            ConnectorResult.partial()  — channels ok, messages failed.
            ConnectorResult.failed()   — channels fetch failed.
        """
        logger.debug("SlackConnector: starting fetch")

        # Step 1 — fetch channels (messages depend on channel IDs)
        try:
            raw_channels = await self._client.get_channels()
        except SlackClientError as exc:
            logger.error("SlackConnector: channels fetch failed — %s", exc.message)
            return ConnectorResult.failed(
                source=self.source_name,
                errors=[f"Channels fetch failed: {exc.message}"],
            )

        # Apply allowlist filter — when SLACK_ALLOWED_CHANNEL_IDS is set,
        # keep only channels whose ID appears in the set.
        if self._allowed:
            raw_channels = [c for c in raw_channels if c.get("id") in self._allowed]
            logger.debug(
                "SlackConnector: allowlist active — %d channel(s) after filtering "
                "(allowlist=%s)",
                len(raw_channels), sorted(self._allowed),
            )

        channel_ids: list[str] = [c.get("id", "") for c in raw_channels if c.get("id")]

        # Step 2 — fetch messages for all channels concurrently
        raw_messages: list[dict[str, Any]] = []
        errors: list[str] = []

        try:
            results = await asyncio.gather(
                *[self._fetch_messages_for(cid) for cid in channel_ids],
                return_exceptions=False,
            )
            for batch in results:
                raw_messages.extend(batch)
        except SlackClientError as exc:
            errors.append(f"Messages fetch failed: {exc.message}")
            logger.warning("SlackConnector: messages fetch failed — %s", exc.message)

        # Normalise whatever data was successfully collected.
        slack_context = self._normalizer.normalize(
            raw_channels=raw_channels,
            raw_messages=raw_messages,
        )
        data: dict[str, Any] = slack_context.model_dump()

        if errors:
            logger.warning("SlackConnector: partial result")
            return ConnectorResult.partial(
                source=self.source_name,
                data=data,
                errors=errors,
            )

        logger.debug("SlackConnector: full success")
        return ConnectorResult.success(
            source=self.source_name,
            data=data,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_messages_for(self, channel_id: str) -> list[dict[str, Any]]:
        """Fetch messages for one channel and inject channel_id into each dict."""
        messages = await self._client.get_messages(channel_id=channel_id)
        for msg in messages:
            msg["channel_id"] = channel_id
        return messages

    # ------------------------------------------------------------------
    # BaseConnector — operational contract
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        Verify that the Slack API is reachable and the bot token is valid.

        Delegates to SlackAPIClient.ping() which returns True/False and
        never raises.

        Returns
        -------
        bool
            True  — Slack API is reachable and the token is valid.
            False — Slack API is unreachable or the token is invalid.
        """
        return await self._client.ping()
