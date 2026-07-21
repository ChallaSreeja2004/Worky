"""
app/recommendations/router.py
==============================
Recommendations router — widget-facing API.

ENDPOINTS
---------
  GET  /api/v1/recommendations
       Build a populated WorkContext via AuthService + ContextBuilder, invoke
       RecommendationService, and return the resulting RecommendationSet.

EXECUTION FLOW
--------------
Production mode (CONNECTOR_MODE=outlook):
  1. Validate user_id query parameter (FastAPI schema).
  2. Call AuthService.get_valid_token(user_id) to obtain a valid access token.
     → 401 if no token exists (user has not authenticated).
  3. Build an OutlookConnector wired to the user's access token.
  4. Call ContextBuilder.build(user_id, connectors, access_token).
  5. Pass the populated WorkContext to RecommendationService.generate().
  6. Return the RecommendationSet to the widget.

Demo mode (CONNECTOR_MODE=demo):
  Steps 1–2 are replaced by a no-op — the demo user has no stored token.
  Step 3 builds a DemoOutlookConnector (no access_token required).
  Steps 4–6 are identical to production.

ERROR MAPPING
-------------
  AuthUserNotFoundError  → 401  (user must authenticate first)
  AuthRefreshError       → 401  (token expired; re-authentication required)
  RecommendationError    → 422  (caller supplied invalid input)
  BobTimeoutError        → 504  (gateway timeout)
  BobNetworkError        → 502  (bad gateway — network-level failure)
  BobServiceError        → 502  (bad gateway — Bob returned a non-200)
  BobResponseError       → 502  (bad gateway — Bob response shape invalid)
  BobConfigError         → 503  (service unavailable — Bob is misconfigured)

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.auth.service           (AuthUserNotFoundError)
  • app.bob.service            (exception types only)
  • app.bob.models             (RecommendationSet — response type)
  • app.config.settings
  • app.connectors.base        (BaseConnector — type annotation only)
  • app.context_builder.builder (ContextBuilder — type annotation only)
  • app.recommendations.dependencies
  • app.recommendations.exceptions
  • app.recommendations.service (RecommendationService type annotation)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.service import AuthRefreshError, AuthService, AuthUserNotFoundError
from app.bob.models import RecommendationSet
from app.bob.service import (
    BobConfigError,
    BobNetworkError,
    BobResponseError,
    BobServiceError,
    BobTimeoutError,
)
from app.config.settings import get_settings
from app.context_builder.builder import ContextBuilder
from app.recommendations.dependencies import (
    get_auth_service_dep,
    get_context_builder,
    get_outlook_connector,
    get_recommendation_service,
)
from app.recommendations.exceptions import RecommendationError
from app.recommendations.service import RecommendationService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=RecommendationSet,
    summary="Generate recommendations for a user",
    description=(
        "Obtains the user's access token, runs the Outlook connector via "
        "ContextBuilder, and returns a RecommendationSet produced by Bob."
    ),
)
async def get_recommendations(
    user_id: str = Query(..., description="Worky-internal user identifier"),
    rec_service: RecommendationService = Depends(get_recommendation_service),
    auth_service: AuthService = Depends(get_auth_service_dep),
    context_builder: ContextBuilder = Depends(get_context_builder),
) -> RecommendationSet:
    """
    Generate a RecommendationSet for the given user.

    In production mode: retrieves a valid access token from AuthService, runs
    the OutlookConnector via ContextBuilder, then delegates to
    RecommendationService → BobCLIService for AI reasoning.

    In demo mode: skips token retrieval, runs DemoOutlookConnector directly,
    then follows the identical path through ContextBuilder and Bob.

    Raises HTTP 401 if the user has not authenticated (no stored token).
    Raises HTTP 422 if user_id is empty (RecommendationError).
    Raises HTTP 504 if Bob times out (BobTimeoutError).
    Raises HTTP 502 if Bob is unreachable or returns an invalid response.
    Raises HTTP 503 if Bob is misconfigured (BobConfigError).
    """
    logger.info("recommendations: generating for user_id=%s", user_id)

    settings = get_settings()
    is_demo = settings.connector_mode == "demo"

    # ------------------------------------------------------------------
    # Step 1 — Obtain a valid access token (production only).
    # In demo mode this step is skipped entirely — no token is needed.
    # ------------------------------------------------------------------
    access_token = ""

    if not is_demo:
        try:
            access_token = await auth_service.get_valid_token(user_id)
        except AuthUserNotFoundError as exc:
            logger.warning(
                "recommendations: user not authenticated — user_id=%s", user_id
            )
            raise HTTPException(status_code=401, detail=exc.message)
        except AuthRefreshError as exc:
            logger.warning(
                "recommendations: token refresh failed, re-auth required — user_id=%s",
                user_id,
            )
            raise HTTPException(status_code=401, detail=exc.message)

    # ------------------------------------------------------------------
    # Step 2 — Build connector and assemble WorkContext.
    # get_outlook_connector() returns DemoOutlookConnector in demo mode
    # and OutlookConnector in production — the rest of the pipeline is
    # identical regardless of which connector is active.
    # ------------------------------------------------------------------
    connector = get_outlook_connector(access_token)
    connectors = [connector]

    work_context = await context_builder.build(
        user_id=user_id,
        connectors=connectors,
        access_token=access_token,
    )

    logger.info(
        "recommendations: context assembled — user_id=%s active_sources=%s mode=%s",
        user_id,
        work_context.active_sources,
        "demo" if is_demo else "outlook",
    )

    # ------------------------------------------------------------------
    # Step 3 — Generate recommendations from the populated WorkContext.
    # ------------------------------------------------------------------
    try:
        recommendation_set = await rec_service.generate(work_context)
    except RecommendationError as exc:
        logger.warning(
            "recommendations: invalid input — user_id=%s — %s", user_id, exc.message
        )
        raise HTTPException(status_code=422, detail=exc.message)
    except BobTimeoutError as exc:
        logger.error(
            "recommendations: Bob timed out — user_id=%s — %s", user_id, str(exc)
        )
        raise HTTPException(status_code=504, detail=str(exc))
    except (BobNetworkError, BobServiceError, BobResponseError) as exc:
        logger.error(
            "recommendations: Bob upstream error — user_id=%s — %s", user_id, str(exc)
        )
        raise HTTPException(status_code=502, detail=str(exc))
    except BobConfigError as exc:
        logger.error(
            "recommendations: Bob misconfigured — user_id=%s — %s", user_id, str(exc)
        )
        raise HTTPException(status_code=503, detail=str(exc))

    logger.info(
        "recommendations: complete — user_id=%s recommendations=%d",
        user_id,
        len(recommendation_set.recommendations),
    )
    return recommendation_set
