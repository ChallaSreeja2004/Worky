"""
app/recommendations/router.py
==============================
Recommendations router — widget-facing API.

ENDPOINTS
---------
  GET  /api/v1/recommendations
       Generate and return a RecommendationSet for the given user.

DESIGN PRINCIPLES
-----------------
  • The router is thin.  All business logic lives in RecommendationService.
  • RecommendationService is never instantiated here — it is injected via
    FastAPI's Depends() mechanism using get_recommendation_service().
  • A minimal WorkContext is constructed from the supplied user_id and passed
    to RecommendationService.generate().
  • Error types raised by RecommendationService and BobService are mapped to
    the correct HTTP status codes here so the service layer stays HTTP-agnostic.

ERROR MAPPING
-------------
  RecommendationError  → 422  (caller supplied invalid input)
  BobTimeoutError      → 504  (gateway timeout)
  BobNetworkError      → 502  (bad gateway — network-level failure)
  BobServiceError      → 502  (bad gateway — Bob returned a non-200)
  BobResponseError     → 502  (bad gateway — Bob response shape invalid)
  BobConfigError       → 503  (service unavailable — Bob is misconfigured)

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.bob.service           (exception types only)
  • app.bob.models            (RecommendationSet — response type)
  • app.context_builder.models
  • app.recommendations.dependencies
  • app.recommendations.exceptions
  • app.recommendations.service (RecommendationService type annotation)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.bob.models import RecommendationSet
from app.bob.service import (
    BobConfigError,
    BobNetworkError,
    BobResponseError,
    BobServiceError,
    BobTimeoutError,
)
from app.context_builder.models import WorkContext
from app.recommendations.dependencies import get_recommendation_service
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
        "Constructs a minimal WorkContext from the supplied user_id, invokes "
        "RecommendationService.generate(), and returns the resulting "
        "RecommendationSet.  The RecommendationService delegates to the "
        "configured BobService (MockBobService in development, IBMBobService "
        "in production)."
    ),
)
async def get_recommendations(
    user_id: str = Query(..., description="Worky-internal user identifier"),
    rec_service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationSet:
    """
    Generate a RecommendationSet for the given user.

    Builds a minimal WorkContext (user_id only — no connector data) and
    passes it to RecommendationService.generate().  Callers that have
    already assembled a richer WorkContext via the Context Builder should
    invoke RecommendationService directly rather than routing through here.

    Raises HTTP 422 if the user_id is missing or empty (RecommendationError).
    Raises HTTP 504 if Bob times out (BobTimeoutError).
    Raises HTTP 502 if Bob is unreachable or returns an invalid response.
    Raises HTTP 503 if Bob is misconfigured (BobConfigError).
    """
    work_context = WorkContext(user_id=user_id)

    logger.info("recommendations: generating for user_id=%s", user_id)

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
