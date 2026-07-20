"""
app/connectors/outlook/router.py
=================================
Outlook connector router — debug/context endpoint.

ENDPOINTS
---------
  GET  /api/v1/connectors/outlook/context
       Collect today's calendar events and email messages for a user.

DESIGN PRINCIPLES
-----------------
  • The router is thin.  All data collection logic lives in OutlookConnector.
  • AuthService is injected via Depends() — never instantiated here.
  • GraphAPIClient, OutlookNormalizer, and OutlookConnector are constructed
    per-request so each request carries a fresh, user-scoped access token.
  • Auth exceptions from AuthService are mapped to HTTP status codes here
    so all service layers stay HTTP-agnostic.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.auth.dependencies
  • app.auth.service   (exception types only)
  • app.connectors.models
  • app.connectors.outlook.graph_client
  • app.connectors.outlook.normalizer
  • app.connectors.outlook.connector
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_auth_service
from app.auth.service import AuthRefreshError, AuthService, AuthUserNotFoundError
from app.connectors.models import ConnectorResult
from app.connectors.outlook.connector import OutlookConnector
from app.connectors.outlook.graph_client import GraphAPIClient
from app.connectors.outlook.normalizer import OutlookNormalizer

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /context
# ---------------------------------------------------------------------------

@router.get(
    "/context",
    response_model=ConnectorResult,
    summary="Collect Outlook context for a user",
    description=(
        "Fetches today's calendar events and unread email messages from "
        "Microsoft Graph for the given user.  Returns a ConnectorResult "
        "with status SUCCESS, PARTIAL, or FAILED depending on which "
        "fetchers succeeded."
    ),
)
async def get_context(
    user_id: str = Query(..., description="Worky-internal user identifier"),
    auth_service: AuthService = Depends(get_auth_service),
) -> ConnectorResult:
    """
    Collect today's Outlook calendar and email data for a user.

    Obtains a valid (auto-refreshed) access token from AuthService, builds a
    per-request GraphAPIClient, and delegates all data collection to
    OutlookConnector.  The connector returns a ConnectorResult regardless of
    partial failures — SUCCESS, PARTIAL, or FAILED are all valid return values
    and are passed through unchanged.

    Raises HTTP 401 if the user has not authenticated or their refresh token
    has expired.
    """
    try:
        access_token = await auth_service.get_valid_token(user_id=user_id)
    except AuthUserNotFoundError as exc:
        logger.warning(
            "outlook/context: user not authenticated — user_id=%s — %s",
            user_id, exc.message,
        )
        raise HTTPException(status_code=401, detail=exc.message)
    except AuthRefreshError as exc:
        logger.error(
            "outlook/context: token refresh failed — user_id=%s — %s",
            user_id, exc.message,
        )
        raise HTTPException(status_code=401, detail=exc.message)

    client = GraphAPIClient(access_token=access_token)
    normalizer = OutlookNormalizer()
    connector = OutlookConnector(graph_client=client, normalizer=normalizer)

    logger.info("outlook/context: starting context collection for user_id=%s", user_id)
    result = await connector.get_context(user_id=user_id, access_token=access_token)
    logger.info(
        "outlook/context: completed — user_id=%s status=%s",
        user_id, result.status.value,
    )
    return result
