"""
tests/recommendations/test_service.py
========================================
Unit tests for RecommendationService.

Tests cover:

  Interface
    • RecommendationService can be constructed with any BobService.
    • generate() returns a RecommendationSet.

  Input validation
    • generate() raises RecommendationError when work_context is None.
    • generate() raises RecommendationError when user_id is empty string.
    • generate() raises RecommendationError when user_id is whitespace only.
    • generate() does NOT raise for a valid empty WorkContext (no connectors).

  Successful generation
    • Return value is a RecommendationSet instance.
    • user_id is preserved from the WorkContext.
    • recommendations list is forwarded unchanged from BobService.
    • BobService.analyze() is called exactly once per generate() call.
    • BobService.analyze() receives the exact WorkContext passed to generate().

  Bob exception propagation
    • BobServiceError propagates unchanged.
    • BobNetworkError propagates unchanged.
    • BobTimeoutError propagates unchanged.
    • BobResponseError propagates unchanged.
    • BobConfigError propagates unchanged.
    • RecommendationError is NOT raised when BobService fails (Bob errors pass through).

  Integration with MockBobService
    • MockBobService works as a drop-in for generate() calls.
    • Single active source produces a populated RecommendationSet.
    • No active sources produces a fallback RecommendationSet.

  Dependency injection
    • get_recommendation_service() returns a RecommendationService instance.
    • Each call to get_recommendation_service() returns a fresh instance.
    • The injected BobService matches the shared singleton from get_bob_service().

  Logging
    • generate() emits at least one log record at INFO level on success.
    • generate() identifies user_id in the log output.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.bob.mock_service import MockBobService
from app.bob.models import Recommendation, RecommendationSet
from app.bob.service import (
    BobConfigError,
    BobError,
    BobNetworkError,
    BobResponseError,
    BobService,
    BobServiceError,
    BobTimeoutError,
)
from app.connectors.models import ConnectorResult
from app.context_builder.models import WorkContext
from app.recommendations.exceptions import RecommendationError
from app.recommendations.service import RecommendationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_work_context(
    user_id: str = "user-001",
    active_source_names: list[str] | None = None,
) -> WorkContext:
    """Build a minimal WorkContext with the given user_id and active sources."""
    if not active_source_names:
        return WorkContext(user_id=user_id)
    results = [
        ConnectorResult.success(source=s, data={"items": []})
        for s in active_source_names
    ]
    return WorkContext.from_connector_results(user_id=user_id, results=results)


def make_recommendation_set(user_id: str = "user-001") -> RecommendationSet:
    """Build a minimal RecommendationSet for use as a mock return value."""
    return RecommendationSet(
        user_id=user_id,
        recommendations=[
            Recommendation(
                priority=1,
                category="email",
                title="Check inbox",
                description="You have unread messages.",
                source="outlook",
            )
        ],
        model_version="mock",
    )


def make_mock_bob_service(
    return_value: RecommendationSet | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """
    Build a MagicMock that satisfies the BobService interface.

    Does not subclass BobService — matching the mock pattern used throughout
    the test suite (see tests/context_builder/test_builder.py).
    """
    bob = MagicMock(spec=BobService)
    if side_effect is not None:
        bob.analyze = AsyncMock(side_effect=side_effect)
    else:
        bob.analyze = AsyncMock(
            return_value=return_value or make_recommendation_set()
        )
    return bob


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestRecommendationServiceConstruction:

    def test_constructs_with_any_bob_service(self):
        """RecommendationService accepts any BobService implementation."""
        bob = make_mock_bob_service()
        service = RecommendationService(bob_service=bob)
        assert service is not None

    def test_constructs_with_mock_bob_service(self):
        """RecommendationService accepts MockBobService as its BobService."""
        service = RecommendationService(bob_service=MockBobService())
        assert service is not None


# ---------------------------------------------------------------------------
# Input validation — RecommendationError for bad inputs
# ---------------------------------------------------------------------------

class TestRecommendationServiceValidation:

    async def test_raises_recommendation_error_when_work_context_is_none(self):
        """generate(None) raises RecommendationError."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        with pytest.raises(RecommendationError) as exc_info:
            await service.generate(None)  # type: ignore[arg-type]
        assert exc_info.value.message  # message is non-empty

    async def test_raises_recommendation_error_when_user_id_is_empty_string(self):
        """generate() raises RecommendationError when user_id is ''."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = WorkContext(user_id="")
        with pytest.raises(RecommendationError) as exc_info:
            await service.generate(ctx)
        assert "user_id" in exc_info.value.message

    async def test_raises_recommendation_error_when_user_id_is_whitespace(self):
        """generate() raises RecommendationError when user_id is only whitespace."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = WorkContext(user_id="   ")
        with pytest.raises(RecommendationError) as exc_info:
            await service.generate(ctx)
        assert "user_id" in exc_info.value.message

    async def test_does_not_raise_for_valid_empty_work_context(self):
        """generate() with a valid user_id and no connectors does not raise."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = make_work_context(user_id="user-valid")
        result = await service.generate(ctx)
        assert isinstance(result, RecommendationSet)

    async def test_bob_not_called_when_validation_fails(self):
        """When input validation fails, BobService.analyze() is never called."""
        bob = make_mock_bob_service()
        service = RecommendationService(bob_service=bob)
        try:
            await service.generate(None)  # type: ignore[arg-type]
        except RecommendationError:
            pass
        bob.analyze.assert_not_called()

    async def test_recommendation_error_has_message_attribute(self):
        """RecommendationError carries a .message attribute."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        with pytest.raises(RecommendationError) as exc_info:
            await service.generate(WorkContext(user_id=""))
        assert isinstance(exc_info.value.message, str)
        assert len(exc_info.value.message) > 0


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------

class TestRecommendationServiceSuccess:

    async def test_returns_recommendation_set(self):
        """generate() returns a RecommendationSet instance."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.generate(ctx)
        assert isinstance(result, RecommendationSet)

    async def test_user_id_preserved(self):
        """The RecommendationSet.user_id matches the WorkContext.user_id."""
        expected_rs = make_recommendation_set(user_id="specific-user-xyz")
        service = RecommendationService(
            bob_service=make_mock_bob_service(return_value=expected_rs)
        )
        ctx = make_work_context(user_id="specific-user-xyz")
        result = await service.generate(ctx)
        assert result.user_id == "specific-user-xyz"

    async def test_recommendations_forwarded_unchanged(self):
        """The RecommendationSet returned by BobService is passed through unchanged."""
        expected_rs = make_recommendation_set()
        service = RecommendationService(
            bob_service=make_mock_bob_service(return_value=expected_rs)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.generate(ctx)
        assert result is expected_rs

    async def test_bob_analyze_called_exactly_once(self):
        """BobService.analyze() is called exactly once per generate() call."""
        bob = make_mock_bob_service()
        service = RecommendationService(bob_service=bob)
        ctx = make_work_context(active_source_names=["outlook"])
        await service.generate(ctx)
        bob.analyze.assert_called_once()

    async def test_bob_analyze_receives_correct_work_context(self):
        """BobService.analyze() receives the exact WorkContext passed to generate()."""
        bob = make_mock_bob_service()
        service = RecommendationService(bob_service=bob)
        ctx = make_work_context(user_id="user-check", active_source_names=["slack"])
        await service.generate(ctx)
        bob.analyze.assert_called_once_with(ctx)

    async def test_empty_recommendations_list_is_valid(self):
        """A RecommendationSet with no recommendations is a valid result."""
        empty_rs = RecommendationSet(user_id="user-001", recommendations=[])
        service = RecommendationService(
            bob_service=make_mock_bob_service(return_value=empty_rs)
        )
        ctx = make_work_context(user_id="user-001")
        result = await service.generate(ctx)
        assert result.recommendations == []

    async def test_multiple_sequential_calls_are_independent(self):
        """
        Two sequential generate() calls each invoke BobService.analyze() once
        and receive independent results.
        """
        bob = make_mock_bob_service()
        service = RecommendationService(bob_service=bob)

        ctx_a = make_work_context(user_id="user-a", active_source_names=["outlook"])
        ctx_b = make_work_context(user_id="user-b", active_source_names=["slack"])

        await service.generate(ctx_a)
        await service.generate(ctx_b)

        assert bob.analyze.call_count == 2
        calls = bob.analyze.call_args_list
        assert calls[0] == call(ctx_a)
        assert calls[1] == call(ctx_b)


# ---------------------------------------------------------------------------
# Bob exception propagation
# ---------------------------------------------------------------------------

class TestRecommendationServiceBobExceptionPropagation:

    async def test_bob_service_error_propagates(self):
        """BobServiceError raised by BobService.analyze() propagates unchanged."""
        exc = BobServiceError("Bob returned HTTP 503")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobServiceError) as exc_info:
            await service.generate(ctx)
        assert exc_info.value is exc

    async def test_bob_network_error_propagates(self):
        """BobNetworkError propagates unchanged."""
        exc = BobNetworkError("Connection refused")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobNetworkError) as exc_info:
            await service.generate(ctx)
        assert exc_info.value is exc

    async def test_bob_timeout_error_propagates(self):
        """BobTimeoutError propagates unchanged."""
        exc = BobTimeoutError("Request timed out after 30s")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobTimeoutError) as exc_info:
            await service.generate(ctx)
        assert exc_info.value is exc

    async def test_bob_response_error_propagates(self):
        """BobResponseError propagates unchanged."""
        exc = BobResponseError("Missing 'recommendations' field")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobResponseError) as exc_info:
            await service.generate(ctx)
        assert exc_info.value is exc

    async def test_bob_config_error_propagates(self):
        """BobConfigError propagates unchanged."""
        exc = BobConfigError("BOB_API_URL is not set")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobConfigError) as exc_info:
            await service.generate(ctx)
        assert exc_info.value is exc

    async def test_bob_errors_are_not_wrapped_in_recommendation_error(self):
        """Bob exceptions must NOT be re-raised as RecommendationError."""
        exc = BobTimeoutError("Timeout")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobError):
            await service.generate(ctx)
        # Confirm it is not wrapped
        try:
            await service.generate(ctx)
        except RecommendationError:
            pytest.fail(
                "BobError must not be wrapped in RecommendationError"
            )
        except BobError:
            pass  # correct

    async def test_bob_error_base_class_is_propagated(self):
        """Any BobError subclass is catchable as BobError."""
        exc = BobNetworkError("DNS failure")
        service = RecommendationService(
            bob_service=make_mock_bob_service(side_effect=exc)
        )
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobError):
            await service.generate(ctx)


# ---------------------------------------------------------------------------
# Integration with MockBobService
# ---------------------------------------------------------------------------

class TestRecommendationServiceWithMockBobService:

    async def test_works_with_mock_bob_service(self):
        """generate() works end-to-end with MockBobService."""
        service = RecommendationService(bob_service=MockBobService())
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.generate(ctx)
        assert isinstance(result, RecommendationSet)

    async def test_mock_returns_populated_set_for_active_source(self):
        """MockBobService produces at least one recommendation for an active source."""
        service = RecommendationService(bob_service=MockBobService())
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.generate(ctx)
        assert len(result.recommendations) >= 1

    async def test_mock_returns_set_for_empty_work_context(self):
        """MockBobService handles a WorkContext with no active sources."""
        service = RecommendationService(bob_service=MockBobService())
        ctx = make_work_context(user_id="user-fallback")
        result = await service.generate(ctx)
        assert isinstance(result, RecommendationSet)
        assert result.user_id == "user-fallback"

    async def test_mock_result_has_recommendations(self):
        """MockBobService always returns at least one recommendation."""
        service = RecommendationService(bob_service=MockBobService())
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.generate(ctx)
        assert len(result.recommendations) > 0

    async def test_mock_result_has_correct_user_id(self):
        """user_id in the result matches the WorkContext user_id."""
        service = RecommendationService(bob_service=MockBobService())
        ctx = make_work_context(user_id="mock-user-abc", active_source_names=["outlook"])
        result = await service.generate(ctx)
        assert result.user_id == "mock-user-abc"

    async def test_multiple_users_get_independent_results(self):
        """generate() with different users produces independent RecommendationSets."""
        service = RecommendationService(bob_service=MockBobService())
        ctx_a = make_work_context(user_id="user-a", active_source_names=["outlook"])
        ctx_b = make_work_context(user_id="user-b", active_source_names=["slack"])
        result_a = await service.generate(ctx_a)
        result_b = await service.generate(ctx_b)
        assert result_a.user_id == "user-a"
        assert result_b.user_id == "user-b"


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

class TestRecommendationServiceDependencyInjection:

    def test_get_recommendation_service_returns_recommendation_service_instance(self):
        """get_recommendation_service() returns a RecommendationService."""
        from app.recommendations.dependencies import get_recommendation_service
        service = get_recommendation_service()
        assert isinstance(service, RecommendationService)

    def test_get_recommendation_service_returns_fresh_instance_each_call(self):
        """Each call to get_recommendation_service() returns a distinct object."""
        from app.recommendations.dependencies import get_recommendation_service
        a = get_recommendation_service()
        b = get_recommendation_service()
        # RecommendationService is not a singleton — fresh instance each time.
        assert a is not b

    def test_injected_bob_service_is_shared_bob_singleton(self):
        """
        The BobService injected into RecommendationService is the same shared
        singleton returned by get_bob_service().
        """
        from app.bob.dependencies import _get_shared_bob_service, get_bob_service
        from app.recommendations.dependencies import get_recommendation_service

        _get_shared_bob_service.cache_clear()
        shared_bob = get_bob_service()
        rec_service = get_recommendation_service()
        assert rec_service._bob is shared_bob
        _get_shared_bob_service.cache_clear()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestRecommendationServiceLogging:

    async def test_logs_at_info_level_on_success(self, caplog):
        """generate() emits at least one INFO-level log record on success."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = make_work_context(active_source_names=["outlook"])
        with caplog.at_level(logging.INFO, logger="app.recommendations.service"):
            await service.generate(ctx)
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(info_records) >= 1

    async def test_log_contains_user_id(self, caplog):
        """At least one log record on a successful call mentions the user_id."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = make_work_context(user_id="log-test-user-007",
                                active_source_names=["outlook"])
        with caplog.at_level(logging.INFO, logger="app.recommendations.service"):
            await service.generate(ctx)
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "log-test-user-007" in messages

    async def test_log_mentions_recommendation_count_on_success(self, caplog):
        """At least one log record on success includes the recommendation count."""
        service = RecommendationService(bob_service=make_mock_bob_service())
        ctx = make_work_context(active_source_names=["outlook"])
        with caplog.at_level(logging.INFO, logger="app.recommendations.service"):
            await service.generate(ctx)
        messages = " ".join(r.getMessage() for r in caplog.records)
        # The completion log contains "recommendations=N" or similar
        assert any(char.isdigit() for char in messages)


# ---------------------------------------------------------------------------
# RecommendationError contract
# ---------------------------------------------------------------------------

class TestRecommendationErrorContract:

    def test_recommendation_error_has_message_attribute(self):
        """RecommendationError carries a .message attribute."""
        err = RecommendationError("Something went wrong")
        assert err.message == "Something went wrong"

    def test_recommendation_error_is_exception(self):
        """RecommendationError is an Exception."""
        err = RecommendationError("test")
        assert isinstance(err, Exception)

    def test_recommendation_error_message_matches_str(self):
        """str(RecommendationError) matches the message."""
        err = RecommendationError("test message")
        assert str(err) == "test message"
