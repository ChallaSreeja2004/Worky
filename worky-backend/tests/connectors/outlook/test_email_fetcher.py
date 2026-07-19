"""
tests/connectors/outlook/test_email_fetcher.py
===============================================
Unit tests for EmailFetcher.

GraphAPIClient is replaced with an AsyncMock on every test — no real HTTP
calls are made.

Coverage:
  • Successful fetch returns the raw message list from response["value"].
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

from app.connectors.outlook.fetchers.email import EmailFetcher
from app.connectors.outlook.graph_client import (
    GraphAuthError,
    GraphRateLimitError,
    GraphServiceError,
)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

MESSAGES: list[dict[str, Any]] = [
    {
        "id": "msg-001",
        "subject": "Q3 Review — action required",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "receivedDateTime": "2024-06-10T08:15:00Z",
        "isRead": False,
        "importance": "high",
        "bodyPreview": "Please review the attached document before EOD.",
        "hasAttachments": True,
    },
    {
        "id": "msg-002",
        "subject": "Team lunch tomorrow",
        "from": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
        "receivedDateTime": "2024-06-10T09:30:00Z",
        "isRead": False,
        "importance": "normal",
        "bodyPreview": "Booking a table at 12:30.",
        "hasAttachments": False,
    },
]


def make_client(return_value: dict[str, Any]) -> AsyncMock:
    """Return a mock GraphAPIClient whose get_messages returns return_value."""
    client = AsyncMock()
    client.get_messages = AsyncMock(return_value=return_value)
    return client


def make_failing_client(exc: Exception) -> AsyncMock:
    """Return a mock GraphAPIClient whose get_messages raises exc."""
    client = AsyncMock()
    client.get_messages = AsyncMock(side_effect=exc)
    return client


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestEmailFetcherSuccess:

    async def test_returns_raw_message_list(self):
        """fetch() extracts and returns response["value"] unchanged."""
        client = make_client({"value": MESSAGES})
        result = await EmailFetcher(client).fetch()
        assert result == MESSAGES

    async def test_returns_exact_objects_not_copies(self):
        """The returned dicts are the same objects — no copying or wrapping."""
        client = make_client({"value": MESSAGES})
        result = await EmailFetcher(client).fetch()
        assert result[0] is MESSAGES[0]
        assert result[1] is MESSAGES[1]

    async def test_calls_get_messages_exactly_once(self):
        """The client method is called exactly once per fetch() call."""
        client = make_client({"value": MESSAGES})
        await EmailFetcher(client).fetch()
        client.get_messages.assert_awaited_once()

    async def test_returns_all_messages_in_order(self):
        """Order from the Graph response is preserved."""
        client = make_client({"value": MESSAGES})
        result = await EmailFetcher(client).fetch()
        assert len(result) == 2
        assert result[0]["id"] == "msg-001"
        assert result[1]["id"] == "msg-002"

    async def test_response_envelope_fields_are_not_included(self):
        """The odata context key is part of the envelope, not the message list."""
        response = {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#...",
            "value": MESSAGES,
        }
        client = make_client(response)
        result = await EmailFetcher(client).fetch()
        # result is the list, not the envelope dict
        assert isinstance(result, list)
        assert "@odata.context" not in result


# ---------------------------------------------------------------------------
# Empty / missing value tests
# ---------------------------------------------------------------------------

class TestEmailFetcherEmpty:

    async def test_empty_value_list_returns_empty_list(self):
        """Graph returns value=[] when there are no matching messages."""
        client = make_client({"value": []})
        result = await EmailFetcher(client).fetch()
        assert result == []

    async def test_missing_value_key_returns_empty_list(self):
        """Defensive: Graph omits 'value' entirely — fetch returns [] not KeyError."""
        client = make_client({})
        result = await EmailFetcher(client).fetch()
        assert result == []

    async def test_missing_value_key_does_not_raise(self):
        """fetch() must not raise when 'value' is absent from the response."""
        client = make_client({"@odata.context": "some-context-url"})
        result = await EmailFetcher(client).fetch()
        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Error propagation tests
# ---------------------------------------------------------------------------

class TestEmailFetcherErrorPropagation:

    async def test_graph_auth_error_propagates(self):
        """GraphAuthError from the client must not be caught — let it propagate."""
        exc = GraphAuthError("token expired")
        client = make_failing_client(exc)
        with pytest.raises(GraphAuthError) as exc_info:
            await EmailFetcher(client).fetch()
        assert exc_info.value is exc

    async def test_graph_rate_limit_error_propagates(self):
        """GraphRateLimitError must propagate so the connector can surface PARTIAL."""
        exc = GraphRateLimitError("rate limited after 3 attempts")
        client = make_failing_client(exc)
        with pytest.raises(GraphRateLimitError) as exc_info:
            await EmailFetcher(client).fetch()
        assert exc_info.value is exc

    async def test_graph_service_error_propagates(self):
        """GraphServiceError (network, timeout, 500, …) must propagate unchanged."""
        exc = GraphServiceError("connection refused")
        client = make_failing_client(exc)
        with pytest.raises(GraphServiceError) as exc_info:
            await EmailFetcher(client).fetch()
        assert exc_info.value is exc

    async def test_error_message_is_preserved(self):
        """The original error message must survive propagation without mutation."""
        exc = GraphAuthError("Access token has expired or is yet to be valid.")
        client = make_failing_client(exc)
        with pytest.raises(GraphAuthError) as exc_info:
            await EmailFetcher(client).fetch()
        assert exc_info.value.message == "Access token has expired or is yet to be valid."
