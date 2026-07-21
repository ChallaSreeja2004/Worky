"""
app/connectors/slack/normalizer.py
====================================
SlackNormalizer — transforms raw Slack API JSON into Worky domain models.

RESPONSIBILITIES
----------------
  • Accept raw channel and message dicts from the fetchers.
  • Map each raw dict to the appropriate Worky domain model.
  • Return a fully populated SlackContext.
  • Handle every optional field defensively using .get() — never assume a key exists.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT make any API calls.
  • It does NOT call SlackAPIClient or any fetcher.
  • It does NOT contain business logic (filtering, sorting, prioritising).

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.slack.models
"""

from __future__ import annotations

import logging
from typing import Any

from app.connectors.slack.models import SlackChannel, SlackContext, SlackMessage

logger = logging.getLogger(__name__)


class SlackNormalizer:
    """
    Pure transformation layer between raw Slack API JSON and Worky models.

    All methods are stateless — the class exists only to group related
    normalization logic.  No instance state is held.

    Usage
    -----
    ::

        normalizer = SlackNormalizer()
        context = normalizer.normalize(
            raw_channels=channels_fetcher_result,
            raw_messages=messages_fetcher_result,
        )
        # context → SlackContext
    """

    def normalize(
        self,
        raw_channels: list[dict[str, Any]],
        raw_messages: list[dict[str, Any]],
    ) -> SlackContext:
        """
        Build a SlackContext from the raw Slack API payloads.

        Parameters
        ----------
        raw_channels : list[dict[str, Any]]
            Raw channel dicts as returned by ChannelsFetcher.fetch().
        raw_messages : list[dict[str, Any]]
            Raw message dicts as returned by MessagesFetcher.fetch().

        Returns
        -------
        SlackContext
            Fully populated normalised context.
        """
        channels = [self._normalize_channel(c) for c in raw_channels]
        messages = [self._normalize_message(m) for m in raw_messages]

        logger.debug(
            "SlackNormalizer: normalised %d channel(s), %d message(s)",
            len(channels), len(messages),
        )

        return SlackContext(channels=channels, messages=messages)

    # ------------------------------------------------------------------
    # Internal normalisation helpers
    # ------------------------------------------------------------------

    def _normalize_channel(self, raw: dict[str, Any]) -> SlackChannel:
        """Map a raw Slack conversations.list item to a SlackChannel."""
        return SlackChannel(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            is_private=raw.get("is_private", False),
        )

    def _normalize_message(self, raw: dict[str, Any]) -> SlackMessage:
        """Map a raw Slack conversations.history item to a SlackMessage."""
        return SlackMessage(
            user=raw.get("user", ""),
            text=raw.get("text", ""),
            timestamp=raw.get("ts", ""),
            channel_id=raw.get("channel_id", ""),
        )
