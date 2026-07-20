"""
app/bob/mock_service.py
========================
MockBobService — deterministic BobService implementation for development and tests.

RESPONSIBILITIES
----------------
  • Implement BobService without calling any external API.
  • Return a deterministic, stable RecommendationSet from any WorkContext.
  • Enable the full pipeline (ContextBuilder → BobService → Recommendation cache)
    to run end-to-end without IBM Bob credentials.
  • Serve as the injected implementation when APP_ENV=development.

WHAT THIS MODULE DOES NOT DO
------------------------------
  • It does NOT call IBM Bob, any network service, or any external API.
  • It does NOT read from any database or cache.
  • It does NOT produce random output — given the same WorkContext, the
    returned recommendations are always structurally consistent (though the
    exact set may reflect the active_sources of the input WorkContext).

DETERMINISM GUARANTEE
---------------------
The mock returns one recommendation per active source in the WorkContext,
plus one general recommendation if no sources are active.  The order and
content are fixed for a given set of source names.  This makes the mock
suitable for snapshot testing and frontend development.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.bob.models
  • app.bob.service   (BobService ABC only)
  • app.context_builder.models  (WorkContext)

It must NOT import from:
  • app.connectors.*
  • app.auth
  • app.config
  • app.recommendations
  • httpx
"""

from __future__ import annotations

import logging

from app.bob.models import Recommendation, RecommendationSet
from app.bob.service import BobService
from app.context_builder.models import WorkContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-source deterministic recommendation templates
# ---------------------------------------------------------------------------
# Each entry produces a single Recommendation whose content clearly indicates
# it originated from the mock — useful for frontend development and debugging.

_SOURCE_TEMPLATES: dict[str, dict] = {
    "outlook": {
        "category": "email",
        "title": "Review high-priority emails from this morning",
        "description": (
            "You have unread high-importance emails in your inbox. "
            "Addressing these first will unblock your team."
        ),
        "action_url": "https://outlook.office.com/mail/inbox",
        "source": "outlook",
    },
    "slack": {
        "category": "message",
        "title": "Respond to pending Slack mentions",
        "description": (
            "You have unread mentions in Slack. "
            "Your teammates may be waiting on your input."
        ),
        "action_url": "",
        "source": "slack",
    },
    "github": {
        "category": "task",
        "title": "Review open pull requests assigned to you",
        "description": (
            "There are pull requests awaiting your review. "
            "Unblocking these will keep the team's velocity high."
        ),
        "action_url": "",
        "source": "github",
    },
    "jira": {
        "category": "task",
        "title": "Update your in-progress Jira tickets",
        "description": (
            "Several tickets assigned to you have not been updated recently. "
            "A quick status update keeps the board accurate."
        ),
        "action_url": "",
        "source": "jira",
    },
}

# Fallback recommendation returned when the WorkContext has no active sources.
_FALLBACK_RECOMMENDATION: dict = {
    "category": "general",
    "title": "No connected data sources — configure Worky",
    "description": (
        "Worky could not collect data from any connected enterprise tool. "
        "Ensure your integrations are set up and your session is active."
    ),
    "action_url": "",
    "source": "worky",
}


class MockBobService(BobService):
    """
    Development-mode BobService that returns deterministic recommendations.

    Returns one Recommendation per active source in the WorkContext, drawn
    from a fixed set of templates.  Unknown sources receive a generic
    recommendation acknowledging the source.

    If the WorkContext has no active sources (all connectors failed),
    returns a single general "no data sources" recommendation.

    No constructor arguments — the mock needs no credentials or config.

    Usage
    -----
    ::

        service = MockBobService()
        recommendation_set = await service.analyze(work_context)
    """

    _MODEL_VERSION: str = "mock"

    async def analyze(self, work_context: WorkContext) -> RecommendationSet:
        """
        Return a deterministic RecommendationSet without calling any API.

        Parameters
        ----------
        work_context : WorkContext
            The assembled work context from the ContextBuilder.

        Returns
        -------
        RecommendationSet
            One Recommendation per active source, ordered by priority.
            Falls back to a single general recommendation when no sources
            are active.
        """
        logger.info(
            "MockBobService: generating mock recommendations — user_id=%s "
            "active_sources=%s",
            work_context.user_id,
            work_context.active_sources,
        )

        recommendations = self._build_recommendations(work_context)

        recommendation_set = RecommendationSet(
            user_id=work_context.user_id,
            recommendations=recommendations,
            model_version=self._MODEL_VERSION,
            metadata={
                "mock": True,
                "active_sources": work_context.active_sources,
            },
        )

        logger.debug(
            "MockBobService: returning %d recommendation(s) for user_id=%s",
            len(recommendations),
            work_context.user_id,
        )

        return recommendation_set

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        work_context: WorkContext,
    ) -> list[Recommendation]:
        """
        Build the recommendation list from the active sources.

        Priority is assigned in the order sources appear in active_sources
        (which preserves the order connectors were registered).  Unknown
        source names receive a generic recommendation so the mock handles
        future connectors gracefully without code changes.
        """
        active = work_context.active_sources

        if not active:
            return [
                Recommendation(
                    priority=1,
                    **_FALLBACK_RECOMMENDATION,
                )
            ]

        recommendations: list[Recommendation] = []
        for priority, source in enumerate(active, start=1):
            template = _SOURCE_TEMPLATES.get(source)
            if template is not None:
                recommendations.append(
                    Recommendation(priority=priority, **template)
                )
            else:
                # Unknown source — produce a generic recommendation so the
                # mock degrades gracefully when new connectors are added.
                recommendations.append(
                    Recommendation(
                        priority=priority,
                        category="general",
                        title=f"Review your {source} activity",
                        description=(
                            f"Worky has collected data from {source!r}. "
                            "Review this source for items that need your attention."
                        ),
                        action_url="",
                        source=source,
                    )
                )

        return recommendations
