"""
tests/connectors/demo/test_connector.py
=========================================
Unit tests for DemoOutlookConnector.

No external HTTP calls are made — DemoOutlookConnector is entirely in-process.

Coverage
--------
  Interface compliance
    • source_name == "outlook" (matches OutlookConnector exactly)
    • Is a concrete subclass of BaseConnector

  get_context()
    • Always returns ConnectorResult with status SUCCESS
    • Returned source field is "outlook"
    • ConnectorResult.data contains "calendar_events" and "emails" keys
    • calendar_events is a non-empty list of dicts
    • emails is a non-empty list of dicts
    • Calendar event dicts contain all required CalendarEvent fields
    • Email dicts contain all required Email fields
    • access_token parameter is accepted but not required to be non-empty
    • user_id parameter is accepted and does not affect the shape of output
    • No errors in the returned ConnectorResult
    • metadata contains connector="demo" and synthetic=True

  Sample data content
    • Calendar events include expected demo subjects
    • Emails include expected demo subjects
    • High-importance email is present

  health_check()
    • Always returns True
    • Never raises
"""

from __future__ import annotations

import pytest

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult, ConnectorStatus
from app.connectors.demo.connector import DemoOutlookConnector


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

class TestDemoOutlookConnectorInterface:

    def test_is_subclass_of_base_connector(self):
        """DemoOutlookConnector must implement BaseConnector."""
        assert issubclass(DemoOutlookConnector, BaseConnector)

    def test_source_name_is_outlook(self):
        """source_name must match OutlookConnector exactly for pipeline transparency."""
        connector = DemoOutlookConnector()
        assert connector.source_name == "outlook"

    def test_instance_is_base_connector(self):
        connector = DemoOutlookConnector()
        assert isinstance(connector, BaseConnector)


# ---------------------------------------------------------------------------
# get_context()
# ---------------------------------------------------------------------------

class TestDemoOutlookConnectorGetContext:

    @pytest.fixture
    def connector(self) -> DemoOutlookConnector:
        return DemoOutlookConnector()

    async def test_returns_connector_result(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert isinstance(result, ConnectorResult)

    async def test_status_is_success(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert result.status == ConnectorStatus.SUCCESS

    async def test_source_is_outlook(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert result.source == "outlook"

    async def test_no_errors(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert result.errors == []

    async def test_data_contains_calendar_events(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert "calendar_events" in result.data

    async def test_data_contains_emails(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert "emails" in result.data

    async def test_calendar_events_is_non_empty_list(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        events = result.data["calendar_events"]
        assert isinstance(events, list)
        assert len(events) > 0

    async def test_emails_is_non_empty_list(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        emails = result.data["emails"]
        assert isinstance(emails, list)
        assert len(emails) > 0

    async def test_calendar_event_has_required_fields(self, connector):
        """Each calendar event dict must have the exact same fields as CalendarEvent."""
        result = await connector.get_context(user_id="u1", access_token="")
        event = result.data["calendar_events"][0]
        required_fields = {
            "id", "subject", "start", "end", "location",
            "organizer_name", "organizer_email",
            "is_all_day", "is_cancelled", "is_online_meeting",
            "join_url", "body_preview",
        }
        assert required_fields.issubset(event.keys())

    async def test_email_has_required_fields(self, connector):
        """Each email dict must have the exact same fields as Email."""
        result = await connector.get_context(user_id="u1", access_token="")
        email = result.data["emails"][0]
        required_fields = {
            "id", "subject", "sender_name", "sender_email",
            "received_at", "is_read", "importance",
            "body_preview", "has_attachments",
        }
        assert required_fields.issubset(email.keys())

    async def test_empty_access_token_is_accepted(self, connector):
        """DemoOutlookConnector does not require an access_token."""
        result = await connector.get_context(user_id="demo-user", access_token="")
        assert result.status == ConnectorStatus.SUCCESS

    async def test_non_empty_access_token_is_ignored(self, connector):
        """Passing a real-looking token is harmless — it is unused."""
        result = await connector.get_context(
            user_id="demo-user",
            access_token="eyJhbGciOiJSUzI1NiJ9.ignored",
        )
        assert result.status == ConnectorStatus.SUCCESS

    async def test_user_id_does_not_affect_output_shape(self, connector):
        """Different user_ids must produce the same data shape."""
        result_a = await connector.get_context(user_id="alice", access_token="")
        result_b = await connector.get_context(user_id="bob",   access_token="")
        assert result_a.status == result_b.status
        assert len(result_a.data["calendar_events"]) == len(result_b.data["calendar_events"])
        assert len(result_a.data["emails"])  == len(result_b.data["emails"])

    async def test_metadata_marks_as_demo(self, connector):
        result = await connector.get_context(user_id="u1", access_token="")
        assert result.metadata.get("connector") == "demo"
        assert result.metadata.get("synthetic") is True


# ---------------------------------------------------------------------------
# Sample data content
# ---------------------------------------------------------------------------

class TestDemoOutlookConnectorContent:

    @pytest.fixture
    async def result(self) -> ConnectorResult:
        return await DemoOutlookConnector().get_context(user_id="u1", access_token="")

    async def test_standup_event_present(self, result):
        subjects = {e["subject"] for e in result.data["calendar_events"]}
        assert "Team Standup" in subjects

    async def test_sprint_planning_event_present(self, result):
        subjects = {e["subject"] for e in result.data["calendar_events"]}
        assert "Sprint Planning" in subjects

    async def test_client_demo_event_present(self, result):
        subjects = {e["subject"] for e in result.data["calendar_events"]}
        assert "Client Demo" in subjects

    async def test_one_on_one_event_present(self, result):
        subjects = {e["subject"] for e in result.data["calendar_events"]}
        assert "1:1 with Manager" in subjects

    async def test_architecture_review_event_present(self, result):
        subjects = {e["subject"] for e in result.data["calendar_events"]}
        assert "Architecture Review" in subjects

    async def test_high_importance_email_present(self, result):
        importances = [e["importance"] for e in result.data["emails"]]
        assert "high" in importances

    async def test_client_presentation_email_present(self, result):
        subjects = {e["subject"] for e in result.data["emails"]}
        assert any("Client Presentation" in s for s in subjects)

    async def test_hr_email_present(self, result):
        subjects = {e["subject"] for e in result.data["emails"]}
        assert any("HR" in s or "Onboarding" in s for s in subjects)

    async def test_code_review_email_present(self, result):
        subjects = {e["subject"] for e in result.data["emails"]}
        assert any("Code Review" in s for s in subjects)

    async def test_security_email_present(self, result):
        subjects = {e["subject"] for e in result.data["emails"]}
        assert any("Security" in s for s in subjects)


# ---------------------------------------------------------------------------
# health_check()
# ---------------------------------------------------------------------------

class TestDemoOutlookConnectorHealthCheck:

    async def test_health_check_returns_true(self):
        connector = DemoOutlookConnector()
        assert await connector.health_check() is True

    async def test_health_check_never_raises(self):
        connector = DemoOutlookConnector()
        try:
            await connector.health_check()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"health_check() raised unexpectedly: {exc}")
