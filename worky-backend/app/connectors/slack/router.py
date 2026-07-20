"""
app/connectors/slack/router.py
================================
Slack connector router — debug/context endpoint.

ENDPOINTS
---------
  GET  /api/v1/connectors/slack/channels
       List all channels the bot can access.

  GET  /api/v1/connectors/slack/context
       Collect channels and latest messages (full ConnectorResult).

DESIGN PRINCIPLES
-----------------
  • The router is thin.  All logic lives in SlackConnector.
  • SlackAPIClient is constructed per-request using the bot token from
    SlackSettings — no AuthService needed.
  • SlackClientError is mapped to HTTP 400 here so the service layer stays
    HTTP-agnostic.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.connectors.models
  • app.connectors.slack.*
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.connectors.models import ConnectorResult
from app.connectors.slack.api_client import SlackAPIClient, SlackClientError
from app.connectors.slack.connector import SlackConnector
from app.connectors.slack.normalizer import SlackNormalizer
from app.connectors.slack.settings import get_slack_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_connector() -> SlackConnector:
    """Construct a SlackConnector using settings from .env."""
    settings = get_slack_settings()
    client = SlackAPIClient(bot_token=settings.slack_bot_token)
    normalizer = SlackNormalizer()
    return SlackConnector(
        api_client=client,
        normalizer=normalizer,
        allowed_channel_ids=settings.allowed_channel_ids,
    )


# ---------------------------------------------------------------------------
# GET /channels
# ---------------------------------------------------------------------------

@router.get(
    "/channels",
    summary="List all Slack channels the bot can access",
)
async def list_channels() -> list[dict]:
    """
    Returns all public and private channels the bot token can see.

    Raises HTTP 400 if the Slack API returns an error (e.g., invalid token,
    missing scope).
    """
    settings = get_slack_settings()
    client = SlackAPIClient(bot_token=settings.slack_bot_token)
    try:
        raw = await client.get_channels()
    except SlackClientError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    return [
        {"id": c.get("id"), "name": c.get("name"), "is_private": c.get("is_private")}
        for c in raw
    ]


# ---------------------------------------------------------------------------
# GET /context
# ---------------------------------------------------------------------------

@router.get(
    "/context",
    response_model=ConnectorResult,
    summary="Collect Slack context (channels + messages)",
)
async def get_context() -> ConnectorResult:
    """
    Fetches all allowed channels and the latest 20 messages from each.

    Returns a ConnectorResult with status SUCCESS, PARTIAL, or FAILED.

    Note: SlackConnector authenticates via the bot token baked into
    SlackAPIClient at construction time.  The access_token argument
    required by the BaseConnector interface is intentionally unused here.
    """
    connector = _build_connector()
    logger.info("slack/context: starting context collection")
    # access_token is unused by SlackConnector — auth is via the bot token
    # already set on SlackAPIClient inside _build_connector().
    result = await connector.get_context()
    logger.info("slack/context: completed — status=%s", result.status.value)
    return result
