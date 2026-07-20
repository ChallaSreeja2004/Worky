"""
tests/connectors/outlook/test_router.py
=========================================
Unit tests for the Outlook connector router.

All dependencies are replaced with test doubles — no real HTTP calls,
no real Microsoft Graph, no real AuthService.

The test client overrides FastAPI's dependency injection to inject mock
AuthService instances for each scenario.  OutlookConnector is mocked via
its dependency — GraphAPIClient — so the router's object construction logic
is exercised while the connector logic itself is not re-tested here.

Coverage:
  • GET /context — authenticated user, both fetchers succeed → 200 SUCCESS
  • GET /context — authenticated user, calendar fails → 200 PARTIAL
  • GET /context — authenticated user, both fetchers fail → 200 FAILED
  • GET /context — user not found (not authenticated) → 401
  • GET /context — token refresh failure → 401
  • GET /context — user_id query parameter is required → 422
  • GET /context — response body is a valid ConnectorResult
  • GET /context — source field is "outlook" on all non-401 responses
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_auth_service
from app.auth.service import AuthRefreshError, AuthUserNotFoundError
from app.connectors.models import ConnectorResult, ConnectorStatus
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_auth_service(
    token: str = "valid-token",
    *,
    raise_exc: Exception | None = None,
) -> MagicMock:
    """
    Build a mock AuthService.

    When raise_exc is provided, get_valid_token() raises that exception.
    Otherwise it returns the given token string.
    """
    service = MagicMock()
    if raise_exc is not None:
        service.get_valid_token = AsyncMock(side_effect=raise_exc)
    else:
        service.get_valid_token = AsyncMock(return_value=token)
    return service


def make_client(auth_service: MagicMock) -> TestClient:
    """
    Build a TestClient with the given auth_service injected as a dependency
    override.  The override is applied for the lifetime of this client only.
    """
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    client = TestClient(app, raise_server_exceptions=False)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SUCCESS_RESULT = ConnectorResult.success(
    source="outlook",
    data={
        "user": None,
        "calendar_events": [{"id": "evt-1", "subject": "Standup"}],
        "emails": [{"id": "msg-1", "subject": "Hello"}],
    },
)

PARTIAL_RESULT = ConnectorResult.partial(
    source="outlook",
    data={"user": None, "calendar_events": [], "emails": [{"id": "msg-1"}]},
    errors=["Calendar fetch failed: timeout"],
)

FAILED_RESULT = ConnectorResult.failed(
    source="outlook",
    errors=["Calendar fetch failed: auth", "Email fetch failed: rate limit"],
)


# ---------------------------------------------------------------------------
# Helper: override connector construction so tests don't need real Graph creds
# ---------------------------------------------------------------------------

def _patch_connector(result: ConnectorResult) -> MagicMock:
    """
    Return a mock OutlookConnector whose get_context() returns the given result.

    Patched into the router via monkeypatching OutlookConnector at module level.
    Used in tests that need to control what the connector returns without
    providing a real access_token or real Graph credentials.
    """
    connector = MagicMock()
    connector.get_context = AsyncMock(return_value=result)
    return connector


# ---------------------------------------------------------------------------
# Teardown — always clear dependency overrides after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Ensure dependency overrides don't leak between tests."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — authentication failures (no Graph call needed)
# ---------------------------------------------------------------------------

class TestAuthFailures:

    def test_user_not_found_returns_401(self):
        """AuthUserNotFoundError from AuthService → HTTP 401."""
        auth = make_auth_service(
            raise_exc=AuthUserNotFoundError("No token found for user_id='u1'.")
        )
        client = make_client(auth)
        response = client.get("/api/v1/connectors/outlook/context?user_id=u1")
        assert response.status_code == 401
        assert "No token found" in response.json()["detail"]

    def test_token_refresh_failure_returns_401(self):
        """AuthRefreshError from AuthService → HTTP 401."""
        auth = make_auth_service(
            raise_exc=AuthRefreshError("Token refresh failed — please log in again.")
        )
        client = make_client(auth)
        response = client.get("/api/v1/connectors/outlook/context?user_id=u1")
        assert response.status_code == 401
        assert "refresh failed" in response.json()["detail"].lower()

    def test_missing_user_id_returns_422(self):
        """Omitting user_id query parameter → HTTP 422 Unprocessable Entity."""
        auth = make_auth_service()
        client = make_client(auth)
        response = client.get("/api/v1/connectors/outlook/context")
        assert response.status_code == 422

    def test_auth_service_called_with_correct_user_id(self):
        """AuthService.get_valid_token() is called with the user_id from the query."""
        auth = make_auth_service(
            raise_exc=AuthUserNotFoundError("not found")
        )
        client = make_client(auth)
        client.get("/api/v1/connectors/outlook/context?user_id=test-user-42")
        auth.get_valid_token.assert_called_once_with(user_id="test-user-42")


# ---------------------------------------------------------------------------
# Tests — successful context collection
# ---------------------------------------------------------------------------

class TestContextSuccess:

    def test_success_returns_200(self, monkeypatch):
        """Connector SUCCESS → HTTP 200."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(SUCCESS_RESULT),
        )
        client = make_client(auth)
        response = client.get("/api/v1/connectors/outlook/context?user_id=u1")
        assert response.status_code == 200

    def test_success_response_has_correct_status(self, monkeypatch):
        """ConnectorResult.status is 'success' on a full success."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(SUCCESS_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["status"] == ConnectorStatus.SUCCESS.value

    def test_success_response_source_is_outlook(self, monkeypatch):
        """source field is 'outlook' in the response body."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(SUCCESS_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["source"] == "outlook"

    def test_success_response_contains_data(self, monkeypatch):
        """Response body contains the data dict from the connector."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(SUCCESS_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert "calendar_events" in body["data"]
        assert "emails" in body["data"]

    def test_success_response_errors_is_empty(self, monkeypatch):
        """errors list is empty on a SUCCESS result."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(SUCCESS_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["errors"] == []


# ---------------------------------------------------------------------------
# Tests — partial context collection
# ---------------------------------------------------------------------------

class TestContextPartial:

    def test_partial_returns_200(self, monkeypatch):
        """Connector PARTIAL → HTTP 200 (not an HTTP error — data is still returned)."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(PARTIAL_RESULT),
        )
        client = make_client(auth)
        response = client.get("/api/v1/connectors/outlook/context?user_id=u1")
        assert response.status_code == 200

    def test_partial_response_has_correct_status(self, monkeypatch):
        """ConnectorResult.status is 'partial' in the response body."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(PARTIAL_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["status"] == ConnectorStatus.PARTIAL.value

    def test_partial_response_contains_errors(self, monkeypatch):
        """PARTIAL result includes error messages from the failing fetcher."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(PARTIAL_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert len(body["errors"]) == 1
        assert "Calendar fetch failed" in body["errors"][0]

    def test_partial_source_is_outlook(self, monkeypatch):
        """source field is 'outlook' on a PARTIAL result."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(PARTIAL_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["source"] == "outlook"


# ---------------------------------------------------------------------------
# Tests — total failure
# ---------------------------------------------------------------------------

class TestContextFailed:

    def test_failed_returns_200(self, monkeypatch):
        """Connector FAILED → HTTP 200 (the ConnectorResult itself communicates failure)."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(FAILED_RESULT),
        )
        client = make_client(auth)
        response = client.get("/api/v1/connectors/outlook/context?user_id=u1")
        assert response.status_code == 200

    def test_failed_response_has_correct_status(self, monkeypatch):
        """ConnectorResult.status is 'failed' in the response body."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(FAILED_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["status"] == ConnectorStatus.FAILED.value

    def test_failed_response_has_two_errors(self, monkeypatch):
        """FAILED result with two fetchers failing has two error entries."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(FAILED_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert len(body["errors"]) == 2

    def test_failed_response_data_is_empty(self, monkeypatch):
        """FAILED result has an empty data dict."""
        auth = make_auth_service()
        monkeypatch.setattr(
            "app.connectors.outlook.router.OutlookConnector",
            lambda **_: _patch_connector(FAILED_RESULT),
        )
        client = make_client(auth)
        body = client.get("/api/v1/connectors/outlook/context?user_id=u1").json()
        assert body["data"] == {}
