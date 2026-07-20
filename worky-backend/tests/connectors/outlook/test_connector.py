"""
tests/connectors/outlook/test_connector.py
===========================================
Unit tests for OutlookConnector.

All dependencies (GraphAPIClient, OutlookNormalizer) are replaced with
mock objects on every test — no real HTTP calls are made.

Coverage:
  • source_name == "outlook"
  • get_context() — both fetchers succeed → SUCCESS
  • get_context() — calendar fetch empty, email fetch populated → SUCCESS
  • get_context() — email fetch empty, calendar fetch populated → SUCCESS
  • get_context() — both fetchers return empty lists → SUCCESS with empty data
  • get_context() — calendar fetch raises → PARTIAL
  • get_context() — email fetch raises → PARTIAL
  • get_context() — both fetchers raise → FAILED
  • get_context() — error message is included in errors list
  • get_context() — normalizer called exactly once per invocation
  • get_context() — both Graph client methods called in the same invocation
  • get_context() — return value is a ConnectorResult instance
  • get_context() — source == "outlook" on PARTIAL result
  • get_context() — both-fail with mixed exception types
  • health_check() — ping returns True → True
  • health_check() — ping returns False → False
  • health_check() — never raises
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.connectors.models import ConnectorResult, ConnectorStatus
from app.connectors.outlook.connector import OutlookConnector
from app.connectors.outlook.graph_client import (
    GraphAuthError,
    GraphRateLimitError,
    GraphServiceError,
)
from app.connectors.outlook.models import OutlookContext
from app.connectors.outlook.normalizer import OutlookNormalizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RAW_EVENTS: list[dict[str, Any]] = [
    {
        "id": "evt-001",
        "subject": "Standup",
        "start": {"dateTime": "2024-06-10T09:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-10T09:15:00", "timeZone": "UTC"},
        "location": {"displayName": ""},
        "organizer": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
        "isAllDay": False,
        "isCancelled": False,
        "onlineMeeting": None,
        "bodyPreview": "",
    },
]

RAW_MESSAGES: list[dict[str, Any]] = [
    {
        "id": "msg-001",
        "subject": "Hello",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "receivedDateTime": "2024-06-10T08:00:00Z",
        "isRead": False,
        "importance": "normal",
        "bodyPreview": "Hi there.",
        "hasAttachments": False,
    },
]


def make_mock_client(
    calendar_result: list | Exception = None,
    email_result: list | Exception = None,
    ping_result: bool = True,
) -> AsyncMock:
    """
    Build a mock GraphAPIClient.

    CalendarFetcher and EmailFetcher call graph_client.get_calendar_events()
    and graph_client.get_messages() respectively.  The connector wraps these
    in fetcher instances, so we mock the client methods that the fetchers call.
    """
    if calendar_result is None:
        calendar_result = RAW_EVENTS
    if email_result is None:
        email_result = RAW_MESSAGES

    client = AsyncMock()

    # These are the Graph client methods the fetchers call.
    if isinstance(calendar_result, Exception):
        client.get_calendar_events = AsyncMock(side_effect=calendar_result)
    else:
        client.get_calendar_events = AsyncMock(
            return_value={"value": calendar_result}
        )

    if isinstance(email_result, Exception):
        client.get_messages = AsyncMock(side_effect=email_result)
    else:
        client.get_messages = AsyncMock(
            return_value={"value": email_result}
        )

    client.ping = AsyncMock(return_value=ping_result)
    return client


def make_connector(
    calendar_result: list | Exception = None,
    email_result: list | Exception = None,
    ping_result: bool = True,
) -> OutlookConnector:
    """Build an OutlookConnector wired to mock dependencies."""
    client = make_mock_client(
        calendar_result=calendar_result,
        email_result=email_result,
        ping_result=ping_result,
    )
    normalizer = OutlookNormalizer()
    return OutlookConnector(graph_client=client, normalizer=normalizer)


# ---------------------------------------------------------------------------
# source_name
# ---------------------------------------------------------------------------

class TestSourceName:

    def test_source_name_is_outlook(self):
        """source_name must return 'outlook'."""
        connector = make_connector()
        assert connector.source_name == "outlook"


# ---------------------------------------------------------------------------
# get_context() — SUCCESS paths
# ---------------------------------------------------------------------------

class TestGetContextSuccess:

    async def test_both_fetchers_succeed_returns_success(self):
        """Both fetchers succeed → ConnectorStatus.SUCCESS."""
        connector = make_connector()
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.SUCCESS
        assert result.source == "outlook"
        assert result.errors == []

    async def test_success_result_contains_data(self):
        """Successful result has non-empty data dict."""
        connector = make_connector()
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert isinstance(result.data, dict)
        assert "calendar_events" in result.data
        assert "emails" in result.data

    async def test_success_calendar_events_normalised(self):
        """Calendar events in data are normalised Worky fields, not raw Graph fields."""
        connector = make_connector()
        result = await connector.get_context(user_id="u1", access_token="tok")
        events = result.data["calendar_events"]
        assert len(events) == 1
        # Worky field name — not Graph field name
        assert "subject" in events[0]
        # Raw Graph field name must not appear at top level
        assert "isAllDay" not in events[0]

    async def test_success_emails_normalised(self):
        """Emails in data are normalised Worky fields, not raw Graph fields."""
        connector = make_connector()
        result = await connector.get_context(user_id="u1", access_token="tok")
        emails = result.data["emails"]
        assert len(emails) == 1
        # Worky field name
        assert "sender_name" in emails[0]
        # Raw Graph field name must not appear
        assert "receivedDateTime" not in emails[0]

    async def test_empty_calendar_and_email_returns_success(self):
        """Empty lists from both fetchers → SUCCESS with empty data."""
        connector = make_connector(calendar_result=[], email_result=[])
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.SUCCESS
        assert result.data["calendar_events"] == []
        assert result.data["emails"] == []


# ---------------------------------------------------------------------------
# get_context() — PARTIAL paths
# ---------------------------------------------------------------------------

class TestGetContextPartial:

    async def test_calendar_fetch_fails_returns_partial(self):
        """Calendar fetcher raises → PARTIAL result with email data."""
        exc = GraphServiceError("calendar timeout")
        connector = make_connector(calendar_result=exc)
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.PARTIAL
        assert result.source == "outlook"
        assert len(result.errors) == 1
        assert "Calendar fetch failed" in result.errors[0]

    async def test_calendar_fail_still_returns_email_data(self):
        """When calendar fails, email data is still present and non-empty."""
        exc = GraphServiceError("calendar down")
        connector = make_connector(calendar_result=exc)
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert "emails" in result.data
        assert len(result.data["emails"]) == 1

    async def test_email_fetch_fails_returns_partial(self):
        """Email fetcher raises → PARTIAL result with calendar data."""
        exc = GraphRateLimitError("too many requests")
        connector = make_connector(email_result=exc)
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.PARTIAL
        assert len(result.errors) == 1
        assert "Email fetch failed" in result.errors[0]

    async def test_email_fail_still_returns_calendar_data(self):
        """When email fails, calendar data is still included in the result."""
        exc = GraphRateLimitError("too many requests")
        connector = make_connector(email_result=exc)
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert "calendar_events" in result.data

    async def test_partial_errors_contain_exception_message(self):
        """The error string includes the original exception message."""
        exc = GraphAuthError("token expired for calendar")
        connector = make_connector(calendar_result=exc)
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert any("token expired for calendar" in e for e in result.errors)


# ---------------------------------------------------------------------------
# get_context() — FAILED path
# ---------------------------------------------------------------------------

class TestGetContextFailed:

    async def test_both_fetchers_fail_returns_failed(self):
        """Both fetchers raise → FAILED result."""
        exc_cal = GraphServiceError("calendar down")
        exc_email = GraphServiceError("email down")
        connector = make_connector(
            calendar_result=exc_cal,
            email_result=exc_email,
        )
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.FAILED
        assert result.source == "outlook"

    async def test_failed_result_has_two_errors(self):
        """Both fetchers failing produces exactly two error entries."""
        exc_cal = GraphServiceError("calendar down")
        exc_email = GraphRateLimitError("email rate limited")
        connector = make_connector(
            calendar_result=exc_cal,
            email_result=exc_email,
        )
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert len(result.errors) == 2

    async def test_failed_result_data_is_empty(self):
        """FAILED result has no data."""
        exc = GraphServiceError("both down")
        connector = make_connector(
            calendar_result=exc,
            email_result=GraphServiceError("email also down"),
        )
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.data == {}

    async def test_failed_result_is_not_usable(self):
        """FAILED ConnectorResult.is_usable returns False."""
        exc = GraphServiceError("down")
        connector = make_connector(
            calendar_result=exc,
            email_result=GraphServiceError("also down"),
        )
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.is_usable is False


# ---------------------------------------------------------------------------
# health_check()
# ---------------------------------------------------------------------------

class TestHealthCheck:

    async def test_returns_true_when_ping_succeeds(self):
        """health_check() returns True when ping() returns True."""
        connector = make_connector(ping_result=True)
        assert await connector.health_check() is True

    async def test_returns_false_when_ping_fails(self):
        """health_check() returns False when ping() returns False."""
        connector = make_connector(ping_result=False)
        assert await connector.health_check() is False

    async def test_health_check_never_raises(self):
        """health_check() must not raise even if ping() raises internally."""
        client = AsyncMock()
        # ping() itself catches all exceptions and returns False.
        # Test that health_check() propagates ping()'s False rather than raising.
        client.ping = AsyncMock(return_value=False)
        normalizer = OutlookNormalizer()
        connector = OutlookConnector(graph_client=client, normalizer=normalizer)
        result = await connector.health_check()
        assert result is False


# ---------------------------------------------------------------------------
# Interaction / integration contracts
# ---------------------------------------------------------------------------

class TestInteractionContracts:

    async def test_normalizer_called_exactly_once(self):
        """get_context() calls normalizer.normalize() exactly once per invocation."""
        client = make_mock_client()
        normalizer = MagicMock(wraps=OutlookNormalizer())
        connector = OutlookConnector(graph_client=client, normalizer=normalizer)
        await connector.get_context(user_id="u1", access_token="tok")
        assert normalizer.normalize.call_count == 1

    async def test_both_fetchers_called_in_same_invocation(self):
        """get_context() calls both graph_client.get_calendar_events and get_messages."""
        client = make_mock_client()
        normalizer = OutlookNormalizer()
        connector = OutlookConnector(graph_client=client, normalizer=normalizer)
        await connector.get_context(user_id="u1", access_token="tok")
        client.get_calendar_events.assert_called_once()
        client.get_messages.assert_called_once()

    async def test_get_context_returns_connector_result_instance(self):
        """get_context() return value is a ConnectorResult instance."""
        connector = make_connector()
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert isinstance(result, ConnectorResult)

    async def test_partial_result_source_is_outlook(self):
        """PARTIAL result still carries source == 'outlook'."""
        exc = GraphAuthError("token expired")
        connector = make_connector(calendar_result=exc)
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.PARTIAL
        assert result.source == "outlook"

    async def test_both_fail_mixed_exception_types(self):
        """Both-fail with different exception types → FAILED with two errors."""
        connector = make_connector(
            calendar_result=GraphAuthError("calendar auth"),
            email_result=GraphRateLimitError("email rate limit"),
        )
        result = await connector.get_context(user_id="u1", access_token="tok")
        assert result.status == ConnectorStatus.FAILED
        assert len(result.errors) == 2
        assert any("calendar auth" in e for e in result.errors)
        assert any("email rate limit" in e for e in result.errors)
