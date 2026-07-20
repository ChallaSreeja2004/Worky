"""
tests/auth/test_router.py
=========================
Integration-level tests for the auth router callback endpoint.

All Microsoft OAuth calls are replaced with mocks — no real credentials
are required and no internet access is performed.

Coverage
--------
  JSON path  (FRONTEND_URL not set):
    • Successful callback returns 200 AuthorizationResponse JSON
    • Invalid state returns 400
    • Microsoft token failure returns 502

  Redirect path  (FRONTEND_URL set):
    • Successful callback returns 302 redirect to {FRONTEND_URL}/auth/success
    • Redirect URL contains user_id, display_name, email as query params
    • Redirect URL does NOT contain access_token, refresh_token, or expires_at
    • Special characters in display_name and email are percent-encoded
    • Invalid state still returns 400 (redirect mode does not suppress errors)
    • Microsoft token failure still returns 502

  Backward-compatibility guarantee:
    • When FRONTEND_URL is None the response is always JSON, never a redirect
"""

from __future__ import annotations

import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_auth_service
from app.auth.models import AuthorizationResponse
from app.auth.service import AuthCodeExchangeError, AuthStateError
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auth_response(
    user_id: str = "user-oid-001",
    display_name: str = "Test User",
    email: str = "test@example.com",
) -> AuthorizationResponse:
    """Build a minimal AuthorizationResponse for test assertions."""
    from datetime import datetime, timedelta, timezone
    return AuthorizationResponse(
        user_id=user_id,
        display_name=display_name,
        email=email,
        access_token="test_access_token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def _make_auth_service(
    auth_response: AuthorizationResponse | None = None,
    *,
    raise_exc: Exception | None = None,
) -> MagicMock:
    """
    Return a mock AuthService whose exchange_code_for_tokens() either returns
    the given AuthorizationResponse or raises the given exception.
    """
    service = MagicMock()
    if raise_exc is not None:
        service.exchange_code_for_tokens = AsyncMock(side_effect=raise_exc)
    else:
        service.exchange_code_for_tokens = AsyncMock(
            return_value=auth_response or _make_auth_response()
        )
    return service


def _make_client(auth_service: MagicMock) -> TestClient:
    """TestClient with the given AuthService injected and redirects disabled."""
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    # allow_redirects=False lets us inspect the 302 Location header directly.
    return TestClient(app, raise_server_exceptions=False, follow_redirects=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Ensure dependency overrides never leak between tests."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# JSON path — FRONTEND_URL not set
# ---------------------------------------------------------------------------

class TestCallbackJsonPath:
    """When FRONTEND_URL is None the callback returns JSON (backward-compat)."""

    def test_success_returns_200_json(self):
        auth = _make_auth_service()
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = None
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    def test_success_json_contains_user_fields(self):
        auth = _make_auth_service(_make_auth_response(
            user_id="uid-001",
            display_name="Alice",
            email="alice@example.com",
        ))
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = None
            body = client.get("/api/v1/auth/callback?code=abc&state=xyz").json()

        assert body["user_id"] == "uid-001"
        assert body["display_name"] == "Alice"
        assert body["email"] == "alice@example.com"

    def test_success_json_contains_access_token(self):
        """The JSON path still includes access_token for API-client compatibility."""
        auth = _make_auth_service()
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = None
            body = client.get("/api/v1/auth/callback?code=abc&state=xyz").json()

        assert "access_token" in body

    def test_invalid_state_returns_400(self):
        auth = _make_auth_service(
            raise_exc=AuthStateError("Unknown or expired state parameter.")
        )
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = None
            response = client.get("/api/v1/auth/callback?code=bad&state=bad_state")

        assert response.status_code == 400

    def test_microsoft_failure_returns_502(self):
        auth = _make_auth_service(
            raise_exc=AuthCodeExchangeError("Microsoft returned 400: Invalid code")
        )
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = None
            response = client.get("/api/v1/auth/callback?code=bad&state=xyz")

        assert response.status_code == 502


# ---------------------------------------------------------------------------
# Redirect path — FRONTEND_URL set
# ---------------------------------------------------------------------------

class TestCallbackRedirectPath:
    """When FRONTEND_URL is set the callback redirects to the frontend."""

    def test_success_returns_302(self):
        auth = _make_auth_service()
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        assert response.status_code == 302

    def test_redirect_points_to_auth_success_route(self):
        auth = _make_auth_service()
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        location = response.headers["location"]
        assert location.startswith("http://localhost:3000/auth/success")

    def test_redirect_contains_user_id(self):
        auth = _make_auth_service(_make_auth_response(user_id="uid-42"))
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(response.headers["location"]).query
        ))
        assert params["user_id"] == "uid-42"

    def test_redirect_contains_display_name_and_email(self):
        auth = _make_auth_service(_make_auth_response(
            display_name="Bob Smith",
            email="bob@example.com",
        ))
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(response.headers["location"]).query
        ))
        assert params["display_name"] == "Bob Smith"
        assert params["email"] == "bob@example.com"

    def test_redirect_does_not_expose_access_token(self):
        auth = _make_auth_service()
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        location = response.headers["location"]
        assert "access_token" not in location
        assert "refresh_token" not in location
        assert "expires_at" not in location

    def test_special_characters_in_display_name_are_encoded(self):
        auth = _make_auth_service(_make_auth_response(
            display_name="O'Brien, Séan",
        ))
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=abc&state=xyz")

        params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(response.headers["location"]).query
        ))
        assert params["display_name"] == "O'Brien, Séan"

    def test_invalid_state_returns_400_not_redirect(self):
        """Errors are never swallowed by redirect mode."""
        auth = _make_auth_service(
            raise_exc=AuthStateError("Unknown or expired state parameter.")
        )
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=bad&state=bad")

        assert response.status_code == 400

    def test_microsoft_failure_returns_502_not_redirect(self):
        auth = _make_auth_service(
            raise_exc=AuthCodeExchangeError("Microsoft returned 400: Invalid code")
        )
        client = _make_client(auth)

        with patch("app.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.frontend_url = "http://localhost:3000"
            response = client.get("/api/v1/auth/callback?code=bad&state=xyz")

        assert response.status_code == 502
