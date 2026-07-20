"""
tests/recommendations/test_router.py
======================================
Router-level tests for GET /api/v1/recommendations.

All BobService / RecommendationService calls are replaced with mocks —
no real IBM Bob API is called and no network I/O occurs.

The test client overrides FastAPI's dependency injection to inject a mock
RecommendationService for each scenario.  This keeps each test focused on
the router's HTTP contract: correct status codes, response shapes, and
error mapping.

Coverage
--------
  Happy path
    • Successful call returns 200 with a valid RecommendationSet JSON body
    • user_id is preserved in the response body
    • recommendations list is forwarded unchanged
    • generate() is called with a WorkContext whose user_id matches the query param
    • An empty recommendations list is a valid 200 response

  Input validation
    • Omitting user_id query parameter → 422 (FastAPI schema validation)

  RecommendationError mapping
    • RecommendationError raised by the service → 422
    • Detail message is forwarded from the exception

  BobError error mapping
    • BobTimeoutError  → 504
    • BobNetworkError  → 502
    • BobServiceError  → 502
    • BobResponseError → 502
    • BobConfigError   → 503

  Dependency injection
    • get_recommendation_service override is honoured by the router
    • generate() is called exactly once per request

  Logging
    • INFO log is emitted on a successful call
    • user_id appears in the log output on success
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.bob.models import Recommendation, RecommendationSet
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
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_recommendation_set(
    user_id: str = "user-001",
    recommendations: list[Recommendation] | None = None,
) -> RecommendationSet:
    """Build a minimal RecommendationSet for use as a mock return value."""
    if recommendations is None:
        recommendations = [
            Recommendation(
                priority=1,
                category="email",
                title="Check inbox",
                description="You have unread messages.",
                source="outlook",
            )
        ]
    return RecommendationSet(
        user_id=user_id,
        recommendations=recommendations,
        model_version="mock",
    )


def make_rec_service(
    return_value: RecommendationSet | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """
    Build a mock RecommendationService.

    When side_effect is given, generate() raises that exception.
    Otherwise generate() returns the given RecommendationSet (or a default one).
    """
    service = MagicMock()
    if side_effect is not None:
        service.generate = AsyncMock(side_effect=side_effect)
    else:
        service.generate = AsyncMock(
            return_value=return_value or make_recommendation_set()
        )
    return service


def make_client(rec_service: MagicMock) -> TestClient:
    """
    Build a TestClient with the given rec_service injected as a dependency
    override.
    """
    app.dependency_overrides[get_recommendation_service] = lambda: rec_service
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Ensure dependency overrides never leak between tests."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestGetRecommendationsSuccess:

    def test_success_returns_200(self):
        """Successful generate() call → HTTP 200."""
        svc = make_rec_service()
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 200

    def test_success_response_is_json(self):
        """Response Content-Type is application/json."""
        svc = make_rec_service()
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.headers["content-type"].startswith("application/json")

    def test_success_response_user_id_preserved(self):
        """user_id in the response body matches the service return value."""
        svc = make_rec_service(return_value=make_recommendation_set(user_id="uid-42"))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=uid-42").json()
        assert body["user_id"] == "uid-42"

    def test_success_response_contains_recommendations(self):
        """Response body contains a recommendations list."""
        svc = make_rec_service()
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)

    def test_success_response_recommendations_forwarded_unchanged(self):
        """The recommendations list from the service is included in the body."""
        rs = make_recommendation_set(user_id="user-001")
        svc = make_rec_service(return_value=rs)
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert len(body["recommendations"]) == len(rs.recommendations)
        assert body["recommendations"][0]["title"] == rs.recommendations[0].title

    def test_success_generate_called_with_correct_user_id(self):
        """generate() receives a WorkContext whose user_id matches the query param."""
        svc = make_rec_service()
        client = make_client(svc)
        client.get("/api/v1/recommendations/?user_id=check-user-99")
        call_args = svc.generate.call_args
        work_context: WorkContext = call_args[0][0]
        assert work_context.user_id == "check-user-99"

    def test_success_generate_called_with_work_context_instance(self):
        """generate() is called with a WorkContext object, not a plain dict."""
        svc = make_rec_service()
        client = make_client(svc)
        client.get("/api/v1/recommendations/?user_id=user-001")
        call_args = svc.generate.call_args
        assert isinstance(call_args[0][0], WorkContext)

    def test_success_generate_called_exactly_once(self):
        """generate() is called exactly once per request."""
        svc = make_rec_service()
        client = make_client(svc)
        client.get("/api/v1/recommendations/?user_id=user-001")
        svc.generate.assert_called_once()

    def test_empty_recommendations_list_returns_200(self):
        """An empty recommendations list is a valid 200 response."""
        rs = make_recommendation_set(user_id="user-001", recommendations=[])
        svc = make_rec_service(return_value=rs)
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 200
        assert response.json()["recommendations"] == []

    def test_response_contains_model_version(self):
        """Response body includes model_version from the RecommendationSet."""
        svc = make_rec_service()
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert "model_version" in body


# ---------------------------------------------------------------------------
# Missing required parameter
# ---------------------------------------------------------------------------

class TestMissingUserIdParameter:

    def test_missing_user_id_returns_422(self):
        """Omitting user_id query parameter → HTTP 422 (FastAPI validation)."""
        svc = make_rec_service()
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/")
        assert response.status_code == 422

    def test_missing_user_id_generate_never_called(self):
        """generate() is never called when user_id is absent."""
        svc = make_rec_service()
        client = make_client(svc)
        client.get("/api/v1/recommendations/")
        svc.generate.assert_not_called()


# ---------------------------------------------------------------------------
# RecommendationError mapping
# ---------------------------------------------------------------------------

class TestRecommendationErrorMapping:

    def test_recommendation_error_returns_422(self):
        """RecommendationError raised by the service → HTTP 422."""
        svc = make_rec_service(
            side_effect=RecommendationError("work_context.user_id must be a non-empty string.")
        )
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 422

    def test_recommendation_error_detail_forwarded(self):
        """The detail field in the 422 response carries the exception message."""
        msg = "work_context.user_id must be a non-empty string."
        svc = make_rec_service(side_effect=RecommendationError(msg))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert body["detail"] == msg


# ---------------------------------------------------------------------------
# Bob error mapping
# ---------------------------------------------------------------------------

class TestBobErrorMapping:

    def test_bob_timeout_error_returns_504(self):
        """BobTimeoutError → HTTP 504 Gateway Timeout."""
        svc = make_rec_service(side_effect=BobTimeoutError("Request timed out after 30s"))
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 504

    def test_bob_network_error_returns_502(self):
        """BobNetworkError → HTTP 502 Bad Gateway."""
        svc = make_rec_service(side_effect=BobNetworkError("Connection refused"))
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 502

    def test_bob_service_error_returns_502(self):
        """BobServiceError → HTTP 502 Bad Gateway."""
        svc = make_rec_service(side_effect=BobServiceError("Bob returned HTTP 503"))
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 502

    def test_bob_response_error_returns_502(self):
        """BobResponseError → HTTP 502 Bad Gateway."""
        svc = make_rec_service(side_effect=BobResponseError("Missing 'recommendations' field"))
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 502

    def test_bob_config_error_returns_503(self):
        """BobConfigError → HTTP 503 Service Unavailable."""
        svc = make_rec_service(side_effect=BobConfigError("BOB_API_URL is not set"))
        client = make_client(svc)
        response = client.get("/api/v1/recommendations/?user_id=user-001")
        assert response.status_code == 503

    def test_bob_timeout_error_detail_forwarded(self):
        """504 response detail contains the BobTimeoutError message."""
        msg = "Request timed out after 30s"
        svc = make_rec_service(side_effect=BobTimeoutError(msg))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert msg in body["detail"]

    def test_bob_network_error_detail_forwarded(self):
        """502 response detail contains the BobNetworkError message."""
        msg = "Connection refused"
        svc = make_rec_service(side_effect=BobNetworkError(msg))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert msg in body["detail"]

    def test_bob_service_error_detail_forwarded(self):
        """502 response detail contains the BobServiceError message."""
        msg = "Bob returned HTTP 503"
        svc = make_rec_service(side_effect=BobServiceError(msg))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert msg in body["detail"]

    def test_bob_response_error_detail_forwarded(self):
        """502 response detail contains the BobResponseError message."""
        msg = "Missing 'recommendations' field"
        svc = make_rec_service(side_effect=BobResponseError(msg))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert msg in body["detail"]

    def test_bob_config_error_detail_forwarded(self):
        """503 response detail contains the BobConfigError message."""
        msg = "BOB_API_URL is not set"
        svc = make_rec_service(side_effect=BobConfigError(msg))
        client = make_client(svc)
        body = client.get("/api/v1/recommendations/?user_id=user-001").json()
        assert msg in body["detail"]


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

class TestDependencyInjection:

    def test_dependency_override_is_honoured(self):
        """The injected mock service — not the real one — is invoked."""
        svc = make_rec_service()
        client = make_client(svc)
        client.get("/api/v1/recommendations/?user_id=user-001")
        # If the override was honoured, generate() was called on our mock.
        svc.generate.assert_called_once()

    def test_different_users_call_generate_with_their_user_id(self):
        """Two consecutive calls pass the correct user_id each time."""
        svc = make_rec_service()
        client = make_client(svc)

        client.get("/api/v1/recommendations/?user_id=alice")
        client.get("/api/v1/recommendations/?user_id=bob")

        assert svc.generate.call_count == 2
        first_ctx: WorkContext = svc.generate.call_args_list[0][0][0]
        second_ctx: WorkContext = svc.generate.call_args_list[1][0][0]
        assert first_ctx.user_id == "alice"
        assert second_ctx.user_id == "bob"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestLogging:

    def test_info_log_emitted_on_success(self, caplog):
        """At least one INFO log record is emitted on a successful call."""
        svc = make_rec_service()
        client = make_client(svc)
        with caplog.at_level(logging.INFO, logger="app.recommendations.router"):
            client.get("/api/v1/recommendations/?user_id=user-001")
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(info_records) >= 1

    def test_user_id_in_log_on_success(self, caplog):
        """The user_id appears in at least one INFO log record on success."""
        svc = make_rec_service()
        client = make_client(svc)
        with caplog.at_level(logging.INFO, logger="app.recommendations.router"):
            client.get("/api/v1/recommendations/?user_id=log-user-007")
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "log-user-007" in messages

    def test_warning_log_on_recommendation_error(self, caplog):
        """A WARNING is logged when RecommendationError is raised."""
        svc = make_rec_service(
            side_effect=RecommendationError("user_id must not be empty")
        )
        client = make_client(svc)
        with caplog.at_level(logging.WARNING, logger="app.recommendations.router"):
            client.get("/api/v1/recommendations/?user_id=user-001")
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1

    def test_error_log_on_bob_timeout(self, caplog):
        """An ERROR is logged when BobTimeoutError is raised."""
        svc = make_rec_service(side_effect=BobTimeoutError("timed out"))
        client = make_client(svc)
        with caplog.at_level(logging.ERROR, logger="app.recommendations.router"):
            client.get("/api/v1/recommendations/?user_id=user-001")
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
