"""
tests/connectors/demo/test_router.py
=======================================
Tests for the demo endpoints:
  POST /api/v1/auth/demo                — synthetic session creation
  GET  /api/v1/connectors/demo/context  — synthetic Outlook context

These tests mount the demo routers directly in a minimal FastAPI app so
the real CONNECTOR_MODE env var is never modified and existing tests are
unaffected.

Coverage
--------
  POST /api/v1/auth/demo
    • Returns HTTP 200
    • Response body is valid JSON
    • user_id field is present and non-empty
    • display_name field is present
    • email field is present
    • is_demo field is True
    • Calling the endpoint twice returns the same user_id (deterministic)

  GET /api/v1/connectors/demo/context
    • Returns HTTP 200
    • Response body is valid JSON
    • status field equals "success"
    • data field contains calendar_events list
    • data field contains emails list
    • calendar_events list is non-empty
    • emails list is non-empty
    • Missing user_id query param → 422
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.connectors.demo.router import auth_router, context_router
from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Minimal test apps — one per router so each is tested in isolation
# ---------------------------------------------------------------------------

def make_auth_app() -> FastAPI:
    """Minimal FastAPI app with only the demo auth router mounted."""
    test_app = FastAPI()
    test_app.include_router(auth_router, prefix="/api/v1/auth")
    return test_app


def make_context_app() -> FastAPI:
    """Minimal FastAPI app with only the demo context router mounted."""
    test_app = FastAPI()
    test_app.include_router(context_router, prefix="/api/v1/connectors/demo")
    return test_app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDemoAuthEndpoint:

    def setup_method(self):
        self.client = TestClient(make_auth_app(), raise_server_exceptions=False)

    def test_returns_200(self):
        """POST /api/v1/auth/demo → HTTP 200."""
        response = self.client.post("/api/v1/auth/demo")
        assert response.status_code == 200

    def test_response_is_json(self):
        """Response Content-Type is application/json."""
        response = self.client.post("/api/v1/auth/demo")
        assert response.headers["content-type"].startswith("application/json")

    def test_user_id_present_and_non_empty(self):
        """Response body contains a non-empty user_id."""
        body = self.client.post("/api/v1/auth/demo").json()
        assert "user_id" in body
        assert body["user_id"] != ""

    def test_display_name_present(self):
        """Response body contains a display_name."""
        body = self.client.post("/api/v1/auth/demo").json()
        assert "display_name" in body
        assert isinstance(body["display_name"], str)

    def test_email_present(self):
        """Response body contains an email field."""
        body = self.client.post("/api/v1/auth/demo").json()
        assert "email" in body
        assert isinstance(body["email"], str)

    def test_is_demo_is_true(self):
        """Response body contains is_demo=True."""
        body = self.client.post("/api/v1/auth/demo").json()
        assert body.get("is_demo") is True

    def test_deterministic_user_id(self):
        """Two calls return the same user_id — demo sessions are deterministic."""
        body_a = self.client.post("/api/v1/auth/demo").json()
        body_b = self.client.post("/api/v1/auth/demo").json()
        assert body_a["user_id"] == body_b["user_id"]


# ---------------------------------------------------------------------------
# GET /api/v1/connectors/demo/context
# ---------------------------------------------------------------------------

class TestDemoContextEndpoint:

    def setup_method(self):
        self.client = TestClient(make_context_app(), raise_server_exceptions=False)

    def test_returns_200(self):
        """GET /api/v1/connectors/demo/context → HTTP 200."""
        response = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user")
        assert response.status_code == 200

    def test_response_is_json(self):
        """Response Content-Type is application/json."""
        response = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user")
        assert response.headers["content-type"].startswith("application/json")

    def test_status_is_success(self):
        """ConnectorResult.status is 'success'."""
        body = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user").json()
        assert body["status"] == "success"

    def test_data_contains_calendar_events(self):
        """ConnectorResult.data contains a calendar_events list."""
        body = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user").json()
        assert "calendar_events" in body["data"]
        assert isinstance(body["data"]["calendar_events"], list)

    def test_data_contains_emails(self):
        """ConnectorResult.data contains an emails list."""
        body = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user").json()
        assert "emails" in body["data"]
        assert isinstance(body["data"]["emails"], list)

    def test_calendar_events_non_empty(self):
        """DemoOutlookConnector returns at least one calendar event."""
        body = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user").json()
        assert len(body["data"]["calendar_events"]) > 0

    def test_emails_non_empty(self):
        """DemoOutlookConnector returns at least one email."""
        body = self.client.get("/api/v1/connectors/demo/context?user_id=demo-user").json()
        assert len(body["data"]["emails"]) > 0

    def test_missing_user_id_returns_422(self):
        """Omitting user_id query parameter returns 422 (FastAPI validation)."""
        response = self.client.get("/api/v1/connectors/demo/context")
        assert response.status_code == 422
