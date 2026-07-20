"""
tests/bob/test_ibm_bob_service.py
===================================
Unit tests for IBMBobService.

All HTTP calls to the IBM Bob API are mocked with respx — no live API calls
are made.  These tests verify that IBMBobService:

  • Validates constructor arguments (BobConfigError on empty URL or key).
  • Builds a correct POST request to /analyze.
  • Parses a well-formed 200 response into a RecommendationSet.
  • Raises BobServiceError on non-200 responses.
  • Raises BobTimeoutError on timeout.
  • Raises BobNetworkError on network failure.
  • Raises BobResponseError on non-JSON response body.
  • Raises BobResponseError when 'recommendations' field is missing.
  • Raises BobResponseError when 'recommendations' contains malformed items.
  • Never logs the API key.
  • Preserves user_id from WorkContext in the RecommendationSet.
  • Includes active_sources and request_id in metadata.

Also tests BobSettings, BobRequest, Recommendation, RecommendationSet,
and the get_bob_service() DI provider.
"""

from __future__ import annotations

from datetime import timezone
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from app.bob.mock_service import MockBobService
from app.bob.models import BobRequest, Recommendation, RecommendationSet
from app.bob.service import (
    BobConfigError,
    BobNetworkError,
    BobResponseError,
    BobServiceError,
    BobTimeoutError,
    IBMBobService,
)
from app.bob.settings import BobSettings, get_bob_settings
from app.connectors.models import ConnectorResult
from app.context_builder.models import WorkContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_API_URL = "https://bob.test.example.com/api/v1"
_TEST_API_KEY = "test-api-key-do-not-use"
_ANALYZE_ENDPOINT = f"{_TEST_API_URL}/analyze"


def make_service(
    api_url: str = _TEST_API_URL,
    api_key: str = _TEST_API_KEY,
    timeout: float = 5.0,
) -> IBMBobService:
    """Build an IBMBobService wired to test credentials."""
    return IBMBobService(api_url=api_url, api_key=api_key, timeout=timeout)


def make_work_context(
    user_id: str = "user-001",
    active_source_names: list[str] | None = None,
) -> WorkContext:
    """Build a minimal WorkContext with the requested active sources."""
    if not active_source_names:
        return WorkContext(user_id=user_id)

    results = [
        ConnectorResult.success(source=s, data={"items": []})
        for s in active_source_names
    ]
    return WorkContext.from_connector_results(user_id=user_id, results=results)


def make_bob_success_response(
    recommendations: list[dict] | None = None,
    model_version: str = "ibm-bob-v1",
) -> dict:
    """Build a valid IBM Bob API response body."""
    if recommendations is None:
        recommendations = [
            {
                "priority": 1,
                "category": "email",
                "title": "Check your inbox",
                "description": "You have unread messages.",
                "action_url": "https://outlook.example.com",
                "source": "outlook",
            }
        ]
    return {
        "recommendations": recommendations,
        "model_version": model_version,
    }


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestIBMBobServiceConstructor:

    def test_raises_bob_config_error_on_empty_api_url(self):
        """Empty api_url raises BobConfigError at construction time."""
        with pytest.raises(BobConfigError) as exc_info:
            IBMBobService(api_url="", api_key=_TEST_API_KEY)
        assert "BOB_API_URL" in exc_info.value.message

    def test_raises_bob_config_error_on_empty_api_key(self):
        """Empty api_key raises BobConfigError at construction time."""
        with pytest.raises(BobConfigError) as exc_info:
            IBMBobService(api_url=_TEST_API_URL, api_key="")
        assert "BOB_API_KEY" in exc_info.value.message

    def test_trailing_slash_stripped_from_api_url(self):
        """Trailing slashes on api_url are stripped to avoid double-slash paths."""
        service = IBMBobService(
            api_url=f"{_TEST_API_URL}/",
            api_key=_TEST_API_KEY,
        )
        assert not service._api_url.endswith("/")

    def test_constructs_successfully_with_valid_args(self):
        """Valid api_url and api_key construct without error."""
        service = make_service()
        assert service is not None


# ---------------------------------------------------------------------------
# Successful API call
# ---------------------------------------------------------------------------

class TestIBMBobServiceSuccess:

    @respx.mock
    async def test_returns_recommendation_set(self):
        """A 200 response with valid body returns a RecommendationSet."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert isinstance(result, RecommendationSet)

    @respx.mock
    async def test_user_id_preserved(self):
        """RecommendationSet.user_id matches the WorkContext.user_id."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(user_id="specific-user-abc")
        result = await service.analyze(ctx)
        assert result.user_id == "specific-user-abc"

    @respx.mock
    async def test_recommendations_parsed_correctly(self):
        """Recommendations from the Bob response are parsed into Recommendation objects."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert isinstance(rec, Recommendation)
        assert rec.priority == 1
        assert rec.category == "email"
        assert rec.source == "outlook"

    @respx.mock
    async def test_multiple_recommendations_parsed(self):
        """Multiple recommendations are all parsed correctly."""
        body = make_bob_success_response(
            recommendations=[
                {
                    "priority": 1,
                    "category": "email",
                    "title": "Email 1",
                    "description": "Desc 1",
                    "action_url": "",
                    "source": "outlook",
                },
                {
                    "priority": 2,
                    "category": "message",
                    "title": "Slack msg",
                    "description": "Desc 2",
                    "action_url": "",
                    "source": "slack",
                },
            ]
        )
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=body)
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        assert len(result.recommendations) == 2

    @respx.mock
    async def test_empty_recommendations_list_is_valid(self):
        """Bob may return an empty recommendations list — this is valid."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json={"recommendations": [], "model_version": "v1"})
        )
        service = make_service()
        ctx = make_work_context()
        result = await service.analyze(ctx)
        assert result.recommendations == []

    @respx.mock
    async def test_model_version_is_set(self):
        """model_version reflects the IBMBobService constant."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert result.model_version == "ibm-bob-v1"

    @respx.mock
    async def test_generated_at_is_utc(self):
        """generated_at is timezone-aware and in UTC."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert result.generated_at.tzinfo is not None
        assert result.generated_at.tzinfo == timezone.utc

    @respx.mock
    async def test_metadata_contains_request_id(self):
        """metadata['request_id'] is present and non-empty."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        result = await service.analyze(ctx)
        assert "request_id" in result.metadata
        assert result.metadata["request_id"] != ""

    @respx.mock
    async def test_metadata_contains_active_sources(self):
        """metadata['active_sources'] reflects the WorkContext active sources."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        result = await service.analyze(ctx)
        assert set(result.metadata["active_sources"]) == {"outlook", "slack"}

    @respx.mock
    async def test_post_sent_to_analyze_endpoint(self):
        """IBMBobService sends a POST to the /analyze path."""
        route = respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        await service.analyze(ctx)
        assert route.called

    @respx.mock
    async def test_authorization_header_sent(self):
        """The Authorization: ApiKey header is sent."""
        route = respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        await service.analyze(ctx)
        sent_request = route.calls[0].request
        assert "Authorization" in sent_request.headers
        assert sent_request.headers["Authorization"].startswith("ApiKey ")

    @respx.mock
    async def test_api_key_not_logged(self, caplog):
        """The API key must never appear in log output."""
        import logging as _logging
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=make_bob_success_response())
        )
        service = make_service(api_key="super-secret-key-xyz")
        ctx = make_work_context(active_source_names=["outlook"])
        with caplog.at_level(_logging.DEBUG, logger="app.bob.service"):
            await service.analyze(ctx)
        for record in caplog.records:
            assert "super-secret-key-xyz" not in record.getMessage()


# ---------------------------------------------------------------------------
# Non-200 HTTP responses
# ---------------------------------------------------------------------------

class TestIBMBobServiceHttpErrors:

    @respx.mock
    async def test_raises_bob_service_error_on_400(self):
        """HTTP 400 raises BobServiceError."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(400, json={"error": "bad request"})
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobServiceError) as exc_info:
            await service.analyze(ctx)
        assert "400" in exc_info.value.message

    @respx.mock
    async def test_raises_bob_service_error_on_401(self):
        """HTTP 401 raises BobServiceError."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(401, json={"error": "unauthorized"})
        )
        service = make_service()
        ctx = make_work_context()
        with pytest.raises(BobServiceError) as exc_info:
            await service.analyze(ctx)
        assert "401" in exc_info.value.message

    @respx.mock
    async def test_raises_bob_service_error_on_500(self):
        """HTTP 500 raises BobServiceError."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(500, json={"error": "internal error"})
        )
        service = make_service()
        ctx = make_work_context()
        with pytest.raises(BobServiceError) as exc_info:
            await service.analyze(ctx)
        assert "500" in exc_info.value.message

    @respx.mock
    async def test_bob_service_error_message_contains_request_id(self):
        """BobServiceError message includes the request_id for log correlation."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(503, json={"error": "service unavailable"})
        )
        service = make_service()
        ctx = make_work_context()
        with pytest.raises(BobServiceError) as exc_info:
            await service.analyze(ctx)
        assert "request_id=" in exc_info.value.message


# ---------------------------------------------------------------------------
# Network and timeout failures
# ---------------------------------------------------------------------------

class TestIBMBobServiceNetworkErrors:

    @respx.mock
    async def test_raises_bob_timeout_error_on_timeout(self):
        """httpx.TimeoutException → BobTimeoutError."""
        import httpx as _httpx
        respx.post(_ANALYZE_ENDPOINT).mock(
            side_effect=_httpx.TimeoutException("timed out")
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobTimeoutError) as exc_info:
            await service.analyze(ctx)
        assert "timed out" in exc_info.value.message.lower() or "timeout" in exc_info.value.message.lower()

    @respx.mock
    async def test_raises_bob_network_error_on_connect_error(self):
        """httpx.ConnectError → BobNetworkError."""
        import httpx as _httpx
        respx.post(_ANALYZE_ENDPOINT).mock(
            side_effect=_httpx.ConnectError("connection refused")
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobNetworkError) as exc_info:
            await service.analyze(ctx)
        assert "Network error" in exc_info.value.message

    @respx.mock
    async def test_bob_network_error_does_not_leak_api_key(self):
        """BobNetworkError message must never contain the API key."""
        import httpx as _httpx
        respx.post(_ANALYZE_ENDPOINT).mock(
            side_effect=_httpx.ConnectError("connection refused")
        )
        service = make_service(api_key="leaked-key-xyz")
        ctx = make_work_context()
        with pytest.raises(BobNetworkError) as exc_info:
            await service.analyze(ctx)
        assert "leaked-key-xyz" not in exc_info.value.message


# ---------------------------------------------------------------------------
# Malformed response bodies
# ---------------------------------------------------------------------------

class TestIBMBobServiceResponseErrors:

    @respx.mock
    async def test_raises_bob_response_error_on_non_json_body(self):
        """Non-JSON 200 response → BobResponseError."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, content=b"not valid json {{{")
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobResponseError) as exc_info:
            await service.analyze(ctx)
        assert "non-JSON" in exc_info.value.message

    @respx.mock
    async def test_raises_bob_response_error_when_recommendations_missing(self):
        """Response JSON without 'recommendations' field → BobResponseError."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json={"model_version": "v1"})
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobResponseError) as exc_info:
            await service.analyze(ctx)
        assert "recommendations" in exc_info.value.message

    @respx.mock
    async def test_raises_bob_response_error_when_recommendations_is_not_list(self):
        """'recommendations' field that is not a list → BobResponseError."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json={"recommendations": "not a list"})
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobResponseError) as exc_info:
            await service.analyze(ctx)
        assert "list" in exc_info.value.message.lower()

    @respx.mock
    async def test_raises_bob_response_error_on_malformed_recommendation_item(self):
        """A recommendation item missing required fields → BobResponseError."""
        body = {
            "recommendations": [
                {"priority": 1}  # missing: category, title, description, source
            ],
            "model_version": "v1",
        }
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json=body)
        )
        service = make_service()
        ctx = make_work_context(active_source_names=["outlook"])
        with pytest.raises(BobResponseError) as exc_info:
            await service.analyze(ctx)
        assert "recommendations[0]" in exc_info.value.message

    @respx.mock
    async def test_response_error_contains_request_id(self):
        """BobResponseError message contains the request_id."""
        respx.post(_ANALYZE_ENDPOINT).mock(
            return_value=Response(200, json={"model_version": "v1"})
        )
        service = make_service()
        ctx = make_work_context()
        with pytest.raises(BobResponseError) as exc_info:
            await service.analyze(ctx)
        assert "request_id=" in exc_info.value.message


# ---------------------------------------------------------------------------
# BobSettings tests
# ---------------------------------------------------------------------------

class TestBobSettings:

    def test_bob_settings_defaults(self):
        """BobSettings has sensible defaults for development."""
        settings = BobSettings(bob_api_url="", bob_api_key="")
        assert settings.bob_api_url == ""
        assert settings.bob_api_key == ""
        assert settings.bob_timeout_seconds == 120.0

    def test_bob_settings_custom_timeout(self):
        """bob_timeout_seconds can be overridden."""
        settings = BobSettings(
            bob_api_url="https://example.com",
            bob_api_key="key",
            bob_timeout_seconds=15.0,
        )
        assert settings.bob_timeout_seconds == 15.0

    def test_get_bob_settings_returns_bob_settings_instance(self):
        """get_bob_settings() returns a BobSettings instance."""
        with patch("app.bob.settings.BobSettings") as MockSettings:
            MockSettings.return_value = BobSettings(bob_api_url="", bob_api_key="")
            get_bob_settings.cache_clear()
            result = get_bob_settings()
            assert isinstance(result, BobSettings)
        get_bob_settings.cache_clear()


# ---------------------------------------------------------------------------
# BobRequest model tests
# ---------------------------------------------------------------------------

class TestBobRequestModel:

    def test_bob_request_requires_context_and_request_id(self):
        """BobRequest requires context and request_id."""
        ctx = make_work_context(active_source_names=["outlook"])
        request = BobRequest(context=ctx, request_id="req-001")
        assert request.request_id == "req-001"
        assert request.context.user_id == ctx.user_id

    def test_bob_request_requested_at_is_utc(self):
        """BobRequest.requested_at defaults to UTC timezone-aware datetime."""
        ctx = make_work_context()
        request = BobRequest(context=ctx, request_id="req-002")
        assert request.requested_at.tzinfo is not None
        assert request.requested_at.tzinfo == timezone.utc

    def test_bob_request_model_dump_is_serialisable(self):
        """BobRequest.model_dump(mode='json') produces a JSON-serialisable dict."""
        import json
        ctx = make_work_context(active_source_names=["outlook"])
        request = BobRequest(context=ctx, request_id="req-003")
        dumped = request.model_dump(mode="json")
        # Must not raise
        serialised = json.dumps(dumped)
        assert '"req-003"' in serialised


# ---------------------------------------------------------------------------
# Recommendation model tests
# ---------------------------------------------------------------------------

class TestRecommendationModel:

    def test_recommendation_priority_must_be_at_least_one(self):
        """priority must be >= 1 (ge=1 constraint)."""
        with pytest.raises(Exception):
            Recommendation(
                priority=0,
                category="email",
                title="Title",
                description="Desc",
                source="outlook",
            )

    def test_recommendation_action_url_defaults_to_empty_string(self):
        """action_url defaults to empty string when not provided."""
        rec = Recommendation(
            priority=1,
            category="email",
            title="Title",
            description="Desc",
            source="outlook",
        )
        assert rec.action_url == ""

    def test_recommendation_model_validate_from_dict(self):
        """Recommendation.model_validate() parses a dict correctly."""
        data = {
            "priority": 2,
            "category": "task",
            "title": "Review PR",
            "description": "Open PR needs review.",
            "action_url": "https://github.com/pr/1",
            "source": "github",
        }
        rec = Recommendation.model_validate(data)
        assert rec.priority == 2
        assert rec.source == "github"
        assert rec.action_url == "https://github.com/pr/1"


# ---------------------------------------------------------------------------
# RecommendationSet model tests
# ---------------------------------------------------------------------------

class TestRecommendationSetModel:

    def test_recommendation_set_defaults(self):
        """RecommendationSet has sensible defaults."""
        rs = RecommendationSet(user_id="user-x")
        assert rs.user_id == "user-x"
        assert rs.recommendations == []
        assert rs.model_version == "unknown"
        assert rs.metadata == {}

    def test_recommendation_set_generated_at_is_utc(self):
        """generated_at defaults to a timezone-aware UTC datetime."""
        rs = RecommendationSet(user_id="user-x")
        assert rs.generated_at.tzinfo is not None
        assert rs.generated_at.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# DI provider tests
# ---------------------------------------------------------------------------

class TestGetBobServiceProvider:

    def test_get_bob_service_returns_bob_service_instance(self):
        """get_bob_service() returns a BobService-compatible instance (BobCLIService)."""
        from app.bob.cli_service import BobCLIService
        from app.bob.dependencies import _get_shared_bob_service, get_bob_service
        _get_shared_bob_service.cache_clear()
        service = get_bob_service()
        assert isinstance(service, BobCLIService)
        _get_shared_bob_service.cache_clear()

    def test_get_bob_service_returns_same_instance_on_repeated_calls(self):
        """get_bob_service() returns the same singleton on every call."""
        from app.bob.dependencies import _get_shared_bob_service, get_bob_service
        _get_shared_bob_service.cache_clear()
        a = get_bob_service()
        b = get_bob_service()
        assert a is b
        _get_shared_bob_service.cache_clear()
