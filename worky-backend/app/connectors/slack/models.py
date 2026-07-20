"""
app/connectors/slack/models.py
================================
Worky-internal Pydantic models for the Slack connector.

These models represent the normalised Slack data that SlackNormalizer produces
and SlackConnector places into ConnectorResult.data.  They are internal domain
models — not mirrors of the Slack API response shapes.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • Pydantic

It must NOT import from any other app module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SlackChannel(BaseModel):
    """
    Normalised representation of a single Slack channel.

    Fields
    ------
    id : str
        Slack channel ID (e.g. "C012AB3CD").

    name : str
        Human-readable channel name without the leading #.

    is_private : bool
        True when this is a private channel or group DM.
    """

    id: str = Field(..., description="Slack channel ID.")
    name: str = Field(default="", description="Channel name (without #).")
    is_private: bool = Field(default=False, description="True for private channels.")


class SlackMessage(BaseModel):
    """
    Normalised representation of a single Slack message.

    Fields
    ------
    user : str
        Slack user ID of the message author.  Empty string for bot/system messages.

    text : str
        Plain-text body of the message.

    timestamp : str
        Slack timestamp string (e.g. "1512085950.000216").  Acts as the message ID.

    channel_id : str
        ID of the channel this message belongs to.
    """

    user: str = Field(default="", description="Slack user ID of the author.")
    text: str = Field(default="", description="Message body.")
    timestamp: str = Field(default="", description="Slack timestamp / message ID.")
    channel_id: str = Field(default="", description="Channel this message belongs to.")


class SlackContext(BaseModel):
    """
    The normalised Slack payload assembled by SlackNormalizer.

    This is the object that SlackConnector places into ConnectorResult.data
    via model_dump().

    Fields
    ------
    channels : list[SlackChannel]
        All channels the bot can access.

    messages : list[SlackMessage]
        Latest messages across all accessible channels (up to 20 per channel).
    """

    channels: list[SlackChannel] = Field(
        default_factory=list,
        description="Channels the bot can access.",
    )

    messages: list[SlackMessage] = Field(
        default_factory=list,
        description="Latest messages across all channels.",
    )

    model_config = {"frozen": False}
