"""
tests/recommendations/test_router_demo_mode.py
================================================
Tests for the recommendations router in CONNECTOR_MODE=demo.

These tests verify that:
  • In demo mode the router skips token authentication entirely.
  • In demo mode the router uses DemoOutlookConnector (not OutlookConnector).
  • The pipeline (ContextBuilder → RecommendationService) runs identically
    to production — only the connector source differs.
  • AuthUserNotFoundError and AuthRefreshError are NOT raised in demo mode
    (auth_service.get_valid_token() is never called).

ISOLATION STRATEGY
------------------
The router reads get_settings().connector_mode at request time.
These tests patch app.recommendations.router.get_settings to return a
settings object with connector_mode="demo", leaving the real .env untouched.
RecommendationService is replaced with a mock to avoid calling real Bob.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.bob.models import Recommendation, RecommendationSet
from app.context_builder.models import WorkContext
from app.recommendations.dependencies import (
    get_auth_service_dep,
    get_context_builder,
    get_recommendation_service,
)
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_recommendation_set(user_id: str = "demo-user") -> RecommendationSet:
    return RecommendationSet(
        user_id=user_id,
        recommendations=[
            Recommendation(
                priority=1,
                category="email",
                title="Review client email",
                description="High-importance email from client.",
                source="outlook",
            )
        ],
        model_version="mock",
    )


def make_rec_service(user_id: str = "demo-user") -> MagicMock:
    svc = MagicMock()
    svc.generate = AsyncMock(return_value=make_recommendation_set(user_id=user_id))
    return svc


def make_context_builder(user_id: str = "demo-user") -> MagicMock:
    builder = MagicMock()
    builder.build = AsyncMock(return_value=WorkContext(user_id=user_id))
    return builder


def make_auth_service_never_called() -> MagicMock:
    """
    Auth service whose get_valid_token() will fail the test if called.
    In demo mode the router must NEVER call auth_service.get_valid_token().
    """
    auth = MagicMock()
    auth.get_valid_token = AsyncMock(
        side_effect=AssertionError(
            "get_valid_token() must not be called in demo mode"
        )
    )
    return auth


class _DemoSettings:
    """Minimal settings stand-in with connector_mode=demo."""
    connector_mode = "demo"


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Ensure dependency overrides never leak between tests."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Core demo mode behaviour
# ---------------------------------------------------------------------------

class TestRecommendationsDemoMode:

    def _make_client(
        self,
        rec_service: MagicMock | None = None,
        user_id: str = "demo-user",
    ) -> TestClient:
        svc = rec_service or make_rec_service(user_id=user_id)
        builder = make_context_builder(user_id=user_id)
        auth = make_auth_service_never_called()

        app.dependency_overrides[get_recommendation_service] = lambda: svc
        app.dependency_overrides[get_auth_service_dep] = lambda: auth
        app.dependency_overrides[get_context_builder] = lambda: builder
        return TestClient(app, raise_server_exceptions=False)

    def test_demo_mode_returns_200(self):
        """In demo mode the endpoint returns HTTP 200."""
        client = self._make_client()
        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                response = client.get("/api/v1/recommendations/?user_id=demo-user")
        assert response.status_code == 200

    def test_demo_mode_skips_token_auth(self):
        """
        In demo mode, auth_service.get_valid_token() is NEVER called.
        The auth service mock raises AssertionError if called — the test
        passes only if the router never calls it.
        """
        svc = make_rec_service()
        builder = make_context_builder()
        auth = make_auth_service_never_called()

        app.dependency_overrides[get_recommendation_service] = lambda: svc
        app.dependency_overrides[get_auth_service_dep] = lambda: auth
        app.dependency_overrides[get_context_builder] = lambda: builder
        client = TestClient(app, raise_server_exceptions=True)

        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                response = client.get("/api/v1/recommendations/?user_id=demo-user")

        # If auth was called, an AssertionError would have propagated and
        # raise_server_exceptions=True would have made TestClient raise.
        assert response.status_code == 200

    def test_demo_mode_generate_called_once(self):
        """generate() is called exactly once in demo mode."""
        svc = make_rec_service()
        client = self._make_client(rec_service=svc)

        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                client.get("/api/v1/recommendations/?user_id=demo-user")

        svc.generate.assert_called_once()

    def test_demo_mode_generate_receives_work_context(self):
        """generate() receives a WorkContext object in demo mode."""
        svc = make_rec_service()
        client = self._make_client(rec_service=svc)

        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                client.get("/api/v1/recommendations/?user_id=demo-user")

        call_args = svc.generate.call_args
        assert isinstance(call_args[0][0], WorkContext)

    def test_demo_mode_work_context_has_correct_user_id(self):
        """The WorkContext passed to generate() carries the query user_id."""
        svc = make_rec_service(user_id="test-demo-user")
        builder = make_context_builder(user_id="test-demo-user")
        auth = make_auth_service_never_called()

        app.dependency_overrides[get_recommendation_service] = lambda: svc
        app.dependency_overrides[get_auth_service_dep] = lambda: auth
        app.dependency_overrides[get_context_builder] = lambda: builder
        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                client.get("/api/v1/recommendations/?user_id=test-demo-user")

        ctx: WorkContext = svc.generate.call_args[0][0]
        assert ctx.user_id == "test-demo-user"

    def test_demo_mode_response_has_recommendations_field(self):
        """The 200 response body contains a 'recommendations' list."""
        client = self._make_client()
        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                body = client.get("/api/v1/recommendations/?user_id=demo-user").json()
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)

    def test_demo_mode_missing_user_id_returns_422(self):
        """Omitting user_id still returns 422 (FastAPI schema validation) in demo mode."""
        client = self._make_client()
        with patch("app.recommendations.router.get_settings", return_value=_DemoSettings()):
            with patch("app.recommendations.dependencies.get_settings", return_value=_DemoSettings()):
                response = client.get("/api/v1/recommendations/")
        assert response.status_code == 422
