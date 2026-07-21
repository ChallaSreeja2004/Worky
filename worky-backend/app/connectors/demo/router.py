"""
app/connectors/demo/router.py
================================
Demo routers — provides both synthetic session creation and Outlook context
for Demo Mode.

ROUTERS
-------
  auth_router
      Mounted at /api/v1/auth by main.py.
      POST /api/v1/auth/demo
           No credentials required.  Returns a synthetic user identity.

  context_router
      Mounted at /api/v1/connectors/demo by main.py.
      GET  /api/v1/connectors/demo/context
           No credentials required.  Returns a ConnectorResult in the
           identical shape produced by GET /api/v1/connectors/outlook/context,
           populated by DemoOutlookConnector.

DESIGN
------
Both routers are ONLY mounted when CONNECTOR_MODE=demo.  They never appear in
production.  Both endpoints are no-ops in terms of authentication — they
require no token and perform no AuthService calls.

Using two separate routers (rather than one router mounted twice) ensures each
prefix receives exactly the endpoint that belongs there, with no stray routes
in Swagger.

The demo context endpoint calls DemoOutlookConnector.get_context() directly.
This is the same connector the recommendations pipeline uses via
get_outlook_connector() in dependencies.py, so displayed Outlook data always
comes from the same synthetic dataset that Bob reasons over.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • Pydantic
  • app.connectors.demo.connector  (DemoOutlookConnector)
  • app.connectors.models          (ConnectorResult)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.connectors.demo.connector import DemoOutlookConnector
from app.connectors.models import ConnectorResult

logger = logging.getLogger(__name__)

# auth_router: mounted at /api/v1/auth — exposes POST /api/v1/auth/demo
auth_router = APIRouter()

# context_router: mounted at /api/v1/connectors/demo — exposes GET /api/v1/connectors/demo/context
context_router = APIRouter()

# Fixed synthetic identity for demo sessions.
_DEMO_USER_ID    = "demo-user"
_DEMO_NAME       = "Demo User"
_DEMO_EMAIL      = "demo@worky.example"


class DemoSessionResponse(BaseModel):
    """
    The synthetic identity returned by the demo auth endpoint.

    Field names match the OAuth callback redirect query parameters exactly
    so the frontend can handle both flows with the same login() call.
    """

    user_id:      str
    display_name: str
    email:        str
    is_demo:      bool = True


@auth_router.post(
    "/demo",
    response_model=DemoSessionResponse,
    summary="Create a demo session",
    description=(
        "Returns a synthetic user identity for Demo Mode. "
        "No Microsoft credentials required. "
        "Only available when CONNECTOR_MODE=demo."
    ),
)
async def create_demo_session() -> DemoSessionResponse:
    """
    Create a synthetic demo session.

    Returns a DemoSessionResponse with fixed identity fields.
    The frontend stores these exactly as it would store the real OAuth
    redirect parameters — no special handling needed.

    Always returns 200.  This endpoint cannot fail.
    """
    logger.info("auth/demo: creating demo session for user_id=%s", _DEMO_USER_ID)
    return DemoSessionResponse(
        user_id=_DEMO_USER_ID,
        display_name=_DEMO_NAME,
        email=_DEMO_EMAIL,
        is_demo=True,
    )


# ---------------------------------------------------------------------------
# GET /context  (mounted under /api/v1/connectors/demo by main.py)
# ---------------------------------------------------------------------------

@context_router.get(
    "/context",
    response_model=ConnectorResult,
    summary="Collect demo Outlook context",
    description=(
        "Returns a ConnectorResult populated by DemoOutlookConnector — the "
        "same synthetic calendar events and emails that the recommendations "
        "pipeline uses.  No Microsoft credentials required.  "
        "Only available when CONNECTOR_MODE=demo."
    ),
)
async def get_demo_context(
    user_id: str = Query(..., description="Worky-internal user identifier"),
) -> ConnectorResult:
    """
    Return synthetic Outlook context for Demo Mode.

    Calls DemoOutlookConnector.get_context() directly — the same connector
    the recommendations router uses via get_outlook_connector().  The
    ConnectorResult shape is identical to the production endpoint so the
    frontend MeetingList and EmailList components require no changes.

    Always returns 200 with status="success".  Cannot fail.
    """
    connector = DemoOutlookConnector()
    result = await connector.get_context(user_id=user_id, access_token="")
    logger.info(
        "demo/context: returning synthetic Outlook data for user_id=%s", user_id
    )
    return result
