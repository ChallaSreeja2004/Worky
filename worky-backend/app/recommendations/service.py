"""
app/recommendations/service.py
================================
RecommendationService — orchestration layer between Context Builder and Bob.

RESPONSIBILITIES
----------------
  • Receive a WorkContext from the caller.
  • Validate that the input is acceptable before forwarding to Bob.
  • Invoke BobService.analyze(work_context) and return the RecommendationSet.
  • Log the start and completion of each generation cycle.
  • Let Bob-specific exceptions (BobError subclasses) propagate unchanged so
    the caller retains full knowledge of the failure mode.
  • Raise RecommendationError only for orchestration-level precondition
    failures that originate within this layer.

WHAT THIS SERVICE DOES NOT DO
------------------------------
  • It does NOT call connectors, fetchers, or the Graph API.
  • It does NOT manage authentication or tokens.
  • It does NOT schedule, cache, or persist results.
  • It does NOT construct a WorkContext — the caller provides it.
  • It does NOT expose any HTTP interface.
  • It does NOT know about Outlook, Slack, GitHub, or any connector schema.
  • It does NOT construct BobService — the injected instance is used as-is.

POSITION IN THE ARCHITECTURE
-----------------------------
::

    ContextBuilder.build(...)
        → WorkContext
        → RecommendationService.generate(work_context)
            → BobService.analyze(work_context)
            → RecommendationSet
        ← RecommendationSet returned to caller

The Recommendation Service is the thin seam that will eventually be called
by a scheduler (Phase 12) and whose output will be stored in a cache before
being served to the widget at GET /api/v1/recommendations.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.bob.service        (BobService interface and BobError hierarchy)
  • app.bob.models         (RecommendationSet — return type only)
  • app.context_builder.models  (WorkContext — input type)
  • app.recommendations.exceptions

It must NOT import from:
  • app.connectors.*
  • app.auth
  • app.config
  • fastapi
"""

from __future__ import annotations

import logging

from app.bob.models import RecommendationSet
from app.bob.service import BobError, BobService
from app.context_builder.models import WorkContext
from app.recommendations.exceptions import RecommendationError

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Orchestrates one recommendation generation cycle.

    Receives a WorkContext, validates it, delegates analysis to the
    injected BobService, and returns the resulting RecommendationSet.

    This service is stateless.  It holds no per-user state and is safe
    to call concurrently from multiple tasks.

    Parameters
    ----------
    bob_service : BobService
        The AI reasoning service to delegate to.  In development this is
        MockBobService; in production it is IBMBobService.  This service
        never constructs BobService directly — it is always injected.

    Usage
    -----
    ::

        service = RecommendationService(bob_service=bob_service)
        recommendation_set = await service.generate(work_context)
    """

    def __init__(self, bob_service: BobService) -> None:
        self._bob = bob_service

    async def generate(self, work_context: WorkContext) -> RecommendationSet:
        """
        Generate a RecommendationSet for the given WorkContext.

        Validates the input, invokes BobService.analyze(), and returns the
        result.  Bob-specific failures are propagated unchanged so the caller
        can decide how to handle them (e.g., retain a previously cached result).

        Parameters
        ----------
        work_context : WorkContext
            The assembled, point-in-time snapshot of the user's enterprise
            environment.  Must not be None and must carry a non-empty user_id.

        Returns
        -------
        RecommendationSet
            The prioritised recommendations produced by IBM Bob (or
            MockBobService in development).  An empty recommendations list
            is a valid result — it means no action items were identified.

        Raises
        ------
        RecommendationError
            If work_context is None or work_context.user_id is empty.
            This is a precondition failure in the calling code.

        BobError (and subclasses)
            BobTimeoutError, BobNetworkError, BobServiceError,
            BobResponseError — propagated directly from BobService.analyze()
            without wrapping.  The caller should catch these to implement
            fallback behaviour (e.g., retaining a stale cached result).
        """
        self._validate(work_context)

        logger.info(
            "RecommendationService: generating recommendations — "
            "user_id=%s active_sources=%s",
            work_context.user_id,
            work_context.active_sources,
        )

        recommendation_set = await self._bob.analyze(work_context)

        logger.info(
            "RecommendationService: generation complete — "
            "user_id=%s recommendations=%d",
            work_context.user_id,
            len(recommendation_set.recommendations),
        )

        return recommendation_set

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(work_context: WorkContext) -> None:
        """
        Raise RecommendationError if the WorkContext fails precondition checks.

        Checks
        ------
        - work_context must not be None.
        - work_context.user_id must be a non-empty string.

        Raises
        ------
        RecommendationError
            With a descriptive message identifying which precondition failed.
        """
        if work_context is None:
            raise RecommendationError(
                "work_context must not be None."
            )
        if not work_context.user_id or not work_context.user_id.strip():
            raise RecommendationError(
                "work_context.user_id must be a non-empty string."
            )
