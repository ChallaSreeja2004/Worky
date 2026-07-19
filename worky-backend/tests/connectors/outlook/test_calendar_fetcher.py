"""
tests/connectors/outlook/test_calendar_fetcher.py
==================================================
Unit tests for CalendarFetcher.

GraphAPIClient is replaced with an AsyncMock on every test — no real HTTP
calls are made.

Coverage:
  • Successful fetch returns the raw event list from response["value"].
  • Graph returns an empty value list → fetch returns [].
  • Graph returns a response with no "value" key → fetch returns [].
  • GraphAuthError raised by the client propagates unchanged.
  • GraphRateLimitError raised by the client propagates unchanged.
  • GraphServiceError raised by the client propagates unchanged.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.connectors.outlook.fetchers.calendar import CalendarFetcher
from app.connectors.outlook.graph_client import (
    GraphAuthError,
    GraphRateLimitError,
    GraphServiceError,
)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

EVENTS: list[dict[str, Any]] = [
    {
        "id": "evt-001",
        "subject": "Sprint planning",
        "start": {"dateTime": "2024-06-10T09:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-10T10:00:00", "timeZone": "UTC"},
        "isAllDay": False,
        "isCancelled": False,
        "organizer": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
        "bodyPreview": "Let's plan the sprint.",
        "location": {"displayName": ""},
        "onlineMeeting": None,
    },
    {
        "id": "evt-002",
        "subject": "1:1 with manager",
        "start": {"dateTime": "2024-06-10T11:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-10T11:30:00", "timeZone": "UTC"},
        "isAllDay": False,
        "isCancelled": False,
        "organizer": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "bodyPreview": "Weekly sync.",
        "location": {"displayName": "Teams"},
        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/join/abc"},
    },
]


def make_client(return_value: dict[str, Any]) -> AsyncMock:
    """Return a mock GraphAPIClient whose get_calendar_events returns return_value."""
    client = AsyncMock()
    client.get_calendar_events = AsyncMock(return_value=return_value)
    return client


def make_failing_client(exc: Exception) -> AsyncMock:
    """Return a mock GraphAPIClient whose get_calendar_events raises exc."""
    client = AsyncMock()
    client.get_calendar_events = AsyncMock(side_effect=exc)
    return client


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestCalendarFetcherSuccess:

    async def test_returns_raw_event_list(self):
        """fetch() extracts and returns response["value"] unchanged."""
        client = make_client({"value": EVENTS})
        result = await CalendarFetcher(client).fetch()
        assert result == EVENTS

    async def test_returns_exact_objects_not_copies(self):
        """The returned dicts are the same objects — no copying or wrapping."""
        client = make_client({"value": EVENTS})
        result = await CalendarFetcher(client).fetch()
        assert result[0] is EVENTS[0]
        assert result[1] is EVENTS[1]

    async def test_calls_get_calendar_events_exactly_once(self):
        """The client method is called exactly once per fetch() call."""
        client = make_client({"value": EVENTS})
        await CalendarFetcher(client).fetch()
        client.get_calendar_events.assert_awaited_once()

    async def test_returns_all_events_in_order(self):
        """Order from the Graph response is preserved."""
        client = make_client({"value": EVENTS})
        result = await CalendarFetcher(client).fetch()
        assert len(result) == 2
        assert result[0]["id"] == "evt-001"
        assert result[1]["id"] == "evt-002"

    async def test_response_envelope_fields_are_not_included(self):
        """The odata context key is part of the envelope, not the event list."""
        response = {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#...",
            "value": EVENTS,
        }
        client = make_client(response)
        result = await CalendarFetcher(client).fetch()
        # result is the list, not the envelope dict
        assert isinstance(result, list)
        assert "@odata.context" not in result


# ---------------------------------------------------------------------------
# Empty / missing value tests
# ---------------------------------------------------------------------------

class TestCalendarFetcherEmpty:

    async def test_empty_value_list_returns_empty_list(self):
        """Graph returns value=[] when there are no events today."""
        client = make_client({"value": []})
        result = await CalendarFetcher(client).fetch()
        assert result == []

    async def test_missing_value_key_returns_empty_list(self):
        """Defensive: Graph omits 'value' entirely — fetch returns [] not KeyError."""
        client = make_client({})
        result = await CalendarFetcher(client).fetch()
        assert result == []

    async def test_missing_value_key_does_not_raise(self):
        """fetch() must not raise when 'value' is absent from the response."""
        client = make_client({"@odata.context": "some-context-url"})
        result = await CalendarFetcher(client).fetch()
        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Error propagation tests
# ---------------------------------------------------------------------------

class TestCalendarFetcherErrorPropagation:

    async def test_graph_auth_error_propagates(self):
        """GraphAuthError from the client must not be caught — let it propagate."""
        exc = GraphAuthError("token expired")
        client = make_failing_client(exc)
        with pytest.raises(GraphAuthError) as exc_info:
            await CalendarFetcher(client).fetch()
        assert exc_info.value is exc

    async def test_graph_rate_limit_error_propagates(self):
        """GraphRateLimitError must propagate so the connector can surface PARTIAL."""
        exc = GraphRateLimitError("rate limited after 3 attempts")
        client = make_failing_client(exc)
        with pytest.raises(GraphRateLimitError) as exc_info:
            await CalendarFetcher(client).fetch()
        assert exc_info.value is exc

    async def test_graph_service_error_propagates(self):
        """GraphServiceError (network, timeout, 500, …) must propagate unchanged."""
        exc = GraphServiceError("connection refused")
        client = make_failing_client(exc)
        with pytest.raises(GraphServiceError) as exc_info:
            await CalendarFetcher(client).fetch()
        assert exc_info.value is exc

    async def test_error_message_is_preserved(self):
        """The original error message must survive propagation without mutation."""
        exc = GraphAuthError("Access token has expired or is yet to be valid.")
        client = make_failing_client(exc)
        with pytest.raises(GraphAuthError) as exc_info:
            await CalendarFetcher(client).fetch()
        assert exc_info.value.message == "Access token has expired or is yet to be valid."
