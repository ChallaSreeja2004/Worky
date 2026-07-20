"""
tests/bob/test_mock_service.py
================================
Unit tests for MockBobService.

MockBobService is the development-mode BobService implementation.
These tests verify that it:

  • Implements the BobService interface.
  • Returns a RecommendationSet (never raises) for any valid WorkContext.
  • Returns one recommendation per active source.
  • Returns a fallback recommendation when no sources are active.
  • Handles unknown source names gracefully.
  • Preserves the user_id from the WorkContext.
  • Returns model_version == "mock".
  • Returns generated_at as a timezone-aware UTC datetime.
  • Returns metadata indicating mock=True.
  • Recommendations are sorted by priority ascending, starting at 1.

All tests are synchronous in setup; only analyze() is async.
No external dependencies are required — MockBobService calls no APIs.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any

import pytest

from app.bob.mock_service import MockBobService
from app.bob.models import Recommendation, RecommendationSet
from app.bob.service import BobService
from app.connectors.models import ConnectorResult, ConnectorStatus
from app.context_builder.models import WorkContext


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_work_context(
    user_id: str = "user-001",
    active_source_names: list[str] | None = None,
) -> WorkContext:
    """
    Build a minimal WorkContext with the requested active sources.

    Sources listed in active_source_names are given SUCCESS status so they
    appear in WorkContext.active_sources.  If None, an empty context is
    returned (no connectors).
    """
    if active_source_names is None:
        return WorkContext(user_id=user_id)

    results = [
        ConnectorResult.success(
            source=source,
            data={"items": []},
        )
        for source in active_source_names
    ]
    return WorkContext.from_connector_results(user_id=user_id, results=results)


def make_failed_work_context(user_id: str = "user-001") -> WorkContext:
    """
    Build a WorkContext where all connectors FAILED.

    active_sources will be empty because no connector returned usable data.
    """
    results = [
        ConnectorResult.failed(source="outlook", errors=["auth error"]),
        ConnectorResult.failed(source="slack", errors=["timeout"]),
    ]
    return WorkContext.from_connector_results(user_id=user_id, results=results)


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

class TestMockBobServiceIsABobService:

    def test_is_subclass_of_bob_service(self):
        """MockBobService must be a concrete implementation of BobService."""
        assert issubclass(MockBobService, BobService)

    def test_instance_is_bob_service(self):
        """A MockBobService instance is assignment-compatible with BobService."""
        service: BobService = MockBobService()
        assert isinstance(service, BobService)


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------

class TestMockBobServiceReturnType:

    async def test_returns_recommendation_set(self):
        """analyze() always returns a RecommendationSet instance."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert isinstance(result, RecommendationSet)

    async def test_user_id_preserved(self):
        """RecommendationSet.user_id matches the WorkContext.user_id."""
        service = MockBobService()
        ctx = make_work_context(user_id="specific-user-xyz")
        result = await service.analyze(ctx)
        assert result.user_id == "specific-user-xyz"

    async def test_model_version_is_mock(self):
        """model_version is always 'mock' for MockBobService."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert result.model_version == "mock"

    async def test_generated_at_is_utc(self):
        """generated_at is timezone-aware and in UTC."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert result.generated_at.tzinfo is not None
        assert result.generated_at.tzinfo == timezone.utc

    async def test_metadata_contains_mock_flag(self):
        """metadata['mock'] is True."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert result.metadata.get("mock") is True

    async def test_metadata_contains_active_sources(self):
        """metadata['active_sources'] reflects the WorkContext active sources."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        assert set(result.metadata["active_sources"]) == {"outlook", "slack"}


# ---------------------------------------------------------------------------
# Recommendation count — one per active source
# ---------------------------------------------------------------------------

class TestMockBobServiceRecommendationCount:

    async def test_one_source_produces_one_recommendation(self):
        """One active source → one recommendation."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 1

    async def test_two_sources_produce_two_recommendations(self):
        """Two active sources → two recommendations."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 2

    async def test_three_sources_produce_three_recommendations(self):
        """Three active sources → three recommendations."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack", "github"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 3

    async def test_empty_active_sources_produces_one_fallback(self):
        """No active sources → exactly one fallback recommendation."""
        service = MockBobService()
        ctx = make_work_context()  # no connectors at all
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 1

    async def test_all_failed_connectors_produces_one_fallback(self):
        """All connectors FAILED (empty active_sources) → one fallback."""
        service = MockBobService()
        ctx = make_failed_work_context()
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 1


# ---------------------------------------------------------------------------
# Recommendation content — known source templates
# ---------------------------------------------------------------------------

class TestMockBobServiceKnownSourceTemplates:

    async def test_outlook_recommendation_category(self):
        """Outlook recommendation has category 'email'."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        rec = result.recommendations[0]
        assert rec.category == "email"

    async def test_outlook_recommendation_source(self):
        """Outlook recommendation has source 'outlook'."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert result.recommendations[0].source == "outlook"

    async def test_slack_recommendation_category(self):
        """Slack recommendation has category 'message'."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["slack"])
        result = await service.analyze(ctx)
        assert result.recommendations[0].category == "message"

    async def test_github_recommendation_category(self):
        """GitHub recommendation has category 'task'."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["github"])
        result = await service.analyze(ctx)
        assert result.recommendations[0].category == "task"

    async def test_known_sources_have_non_empty_title(self):
        """All known-source recommendations have a non-empty title."""
        service = MockBobService()
        for source in ("outlook", "slack", "github", "jira"):
            ctx = make_work_context(active_source_names=[source])
            result = await service.analyze(ctx)
            assert result.recommendations[0].title != ""

    async def test_known_sources_have_non_empty_description(self):
        """All known-source recommendations have a non-empty description."""
        service = MockBobService()
        for source in ("outlook", "slack", "github", "jira"):
            ctx = make_work_context(active_source_names=[source])
            result = await service.analyze(ctx)
            assert result.recommendations[0].description != ""


# ---------------------------------------------------------------------------
# Recommendation content — unknown source
# ---------------------------------------------------------------------------

class TestMockBobServiceUnknownSource:

    async def test_unknown_source_produces_recommendation(self):
        """An unknown source name still produces a recommendation without error."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["salesforce"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 1

    async def test_unknown_source_recommendation_category_is_general(self):
        """Unknown source recommendation has category 'general'."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["salesforce"])
        result = await service.analyze(ctx)
        assert result.recommendations[0].category == "general"

    async def test_unknown_source_recommendation_source_matches(self):
        """Unknown source recommendation carries the correct source name."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["salesforce"])
        result = await service.analyze(ctx)
        assert result.recommendations[0].source == "salesforce"

    async def test_unknown_source_mixed_with_known(self):
        """Mix of known and unknown sources all produce recommendations."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "salesforce"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 2
        sources = {r.source for r in result.recommendations}
        assert "outlook" in sources
        assert "salesforce" in sources


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestMockBobServicePriority:

    async def test_first_recommendation_has_priority_one(self):
        """The first recommendation always has priority 1."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        priorities = [r.priority for r in result.recommendations]
        assert priorities[0] == 1

    async def test_priorities_are_sequential_from_one(self):
        """Priorities are 1, 2, 3, … in order."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack", "github"])
        result = await service.analyze(ctx)
        priorities = [r.priority for r in result.recommendations]
        assert priorities == list(range(1, len(priorities) + 1))

    async def test_fallback_recommendation_has_priority_one(self):
        """The fallback (no active sources) recommendation has priority 1."""
        service = MockBobService()
        ctx = make_work_context()
        result = await service.analyze(ctx)
        assert result.recommendations[0].priority == 1


# ---------------------------------------------------------------------------
# Fallback recommendation content
# ---------------------------------------------------------------------------

class TestMockBobServiceFallback:

    async def test_fallback_category_is_general(self):
        """Fallback recommendation has category 'general'."""
        service = MockBobService()
        ctx = make_work_context()
        result = await service.analyze(ctx)
        assert result.recommendations[0].category == "general"

    async def test_fallback_has_non_empty_title(self):
        """Fallback recommendation has a non-empty title."""
        service = MockBobService()
        ctx = make_work_context()
        result = await service.analyze(ctx)
        assert result.recommendations[0].title != ""

    async def test_fallback_has_non_empty_description(self):
        """Fallback recommendation has a non-empty description."""
        service = MockBobService()
        ctx = make_work_context()
        result = await service.analyze(ctx)
        assert result.recommendations[0].description != ""


# ---------------------------------------------------------------------------
# Recommendation model validation
# ---------------------------------------------------------------------------

class TestRecommendationModelValidation:

    async def test_each_recommendation_is_recommendation_instance(self):
        """Every item in recommendations is a Recommendation instance."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        for rec in result.recommendations:
            assert isinstance(rec, Recommendation)

    async def test_recommendation_priority_is_positive_int(self):
        """Every recommendation's priority is a positive integer."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        for rec in result.recommendations:
            assert isinstance(rec.priority, int)
            assert rec.priority >= 1

    async def test_recommendation_fields_are_strings(self):
        """category, title, description, source are all non-empty strings."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        rec = result.recommendations[0]
        for field_name in ("category", "title", "description", "source"):
            val = getattr(rec, field_name)
            assert isinstance(val, str), f"{field_name} must be str"
            assert val != "", f"{field_name} must be non-empty"

    async def test_recommendation_action_url_is_string(self):
        """action_url is always a string (may be empty)."""
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert isinstance(result.recommendations[0].action_url, str)


# ---------------------------------------------------------------------------
# Stateless / idempotency
# ---------------------------------------------------------------------------

class TestMockBobServiceStateless:

    async def test_same_context_produces_consistent_structure(self):
        """
        Calling analyze() twice with the same WorkContext produces the same
        number of recommendations and the same sources.
        MockBobService must be stateless — repeated calls must not accumulate.
        """
        service = MockBobService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])

        result_1 = await service.analyze(ctx)
        result_2 = await service.analyze(ctx)

        assert len(result_1.recommendations) == len(result_2.recommendations)
        sources_1 = {r.source for r in result_1.recommendations}
        sources_2 = {r.source for r in result_2.recommendations}
        assert sources_1 == sources_2

    async def test_different_users_are_independent(self):
        """Separate users get independent RecommendationSets with their own user_id."""
        service = MockBobService()
        ctx_a = make_work_context(user_id="user-alpha", active_source_names=["outlook"])
        ctx_b = make_work_context(user_id="user-beta", active_source_names=["slack"])

        result_a = await service.analyze(ctx_a)
        result_b = await service.analyze(ctx_b)

        assert result_a.user_id == "user-alpha"
        assert result_b.user_id == "user-beta"
        assert result_a.recommendations[0].source == "outlook"
        assert result_b.recommendations[0].source == "slack"
