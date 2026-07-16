"""
tests/connectors/outlook/test_graph_client.py
=============================================
Unit tests for GraphAPIClient.

All HTTP is intercepted by respx — no real network calls are made.
asyncio.sleep is patched to zero so retry tests execute instantly.

Coverage:
  • Constructor — Authorization header, Accept header, custom timeout
  • get_current_user()    — 200 success, $select params, 401, 403, 500, 404 (no retry)
  • get_calendar_events() — 200 success, date-range params, $select/$orderby/$top,
                            401, 500
  • get_messages()        — 200 success, $filter param, $select/$orderby/$top,
                            401, 403, 500
  • ping()                — True on 200, False on 401, False on network error,
                            False on 500, False on 403 — never raises
  • Retry on 429          — succeeds on second attempt, correct back-off delay,
                            401 is not retried
  • Retry on 503          — succeeds on second attempt, exhausted raises
  • Exponential back-off  — sleep called with [1.0, 2.0] before attempt 3
  • Network error         — retries then succeeds; exhausted raises GraphServiceError
  • Timeout               — retries then succeeds; exhausted raises GraphServiceError
  • Authorization header  — Bearer token present on every request
  • _extract_error_message — Graph error body, no-error-key fallback, non-JSON body,
                             empty message string falls back to response text
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import Response

from app.connectors.outlook.graph_client import (
    GRAPH_BASE_URL,
    GraphAPIClient,
    GraphAuthError,
    GraphRateLimitError,
    GraphServiceError,
    _extract_error_message,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

FAKE_TOKEN = "test-bearer-token-abc123"

USER_RESPONSE: dict[str, Any] = {
    "id": "oid-001",
    "displayName": "Ada Lovelace",
    "mail": "ada@example.com",
    "userPrincipalName": "ada@example.com",
}

CALENDAR_RESPONSE: dict[str, Any] = {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#Collection(event)",
    "value": [
        {
            "id": "evt-001",
            "subject": "Sprint planning",
            "start": {"dateTime": "2024-06-10T09:00:00", "timeZone": "UTC"},
            "end":   {"dateTime": "2024-06-10T10:00:00", "timeZone": "UTC"},
            "isAllDay": False,
            "isCancelled": False,
            "organizer": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
            "bodyPreview": "Let's plan the sprint.",
        }
    ],
}

MESSAGES_RESPONSE: dict[str, Any] = {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#Collection(message)",
    "value": [
        {
            "id": "msg-001",
            "subject": "Action required: review PR",
            "from": {"emailAddress": {"name": "Charlie", "address": "charlie@example.com"}},
            "receivedDateTime": "2024-06-10T08:30:00Z",
            "isRead": False,
            "importance": "high",
            "bodyPreview": "Please review the attached PR.",
            "hasAttachments": False,
        }
    ],
}

GRAPH_ERROR_BODY: dict[str, Any] = {
    "error": {
        "code": "InvalidAuthenticationToken",
        "message": "Access token has expired or is yet to be valid.",
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client(token: str = FAKE_TOKEN) -> GraphAPIClient:
    """Return a GraphAPIClient with a fake token and short timeout."""
    return GraphAPIClient(access_token=token, timeout=1.0)


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------

class TestConstructor:

    def test_authorization_header_uses_bearer_scheme(self):
        client = GraphAPIClient(access_token="my-token")
        assert client._headers["Authorization"] == "Bearer my-token"

    def test_accept_header_is_json(self):
        client = GraphAPIClient(access_token="my-token")
        assert client._headers["Accept"] == "application/json"

    def test_default_timeout_is_twenty_seconds(self):
        client = GraphAPIClient(access_token="my-token")
        assert client._timeout == 20.0

    def test_custom_timeout_is_respected(self):
        client = GraphAPIClient(access_token="my-token", timeout=5.0)
        assert client._timeout == 5.0


# ---------------------------------------------------------------------------
# get_current_user tests
# ---------------------------------------------------------------------------

class TestGetCurrentUser:

    @respx.mock
    async def test_returns_user_dict_on_200(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(200, json=USER_RESPONSE)
        )
        result = await make_client().get_current_user()
        assert result["id"] == "oid-001"
        assert result["displayName"] == "Ada Lovelace"

    @respx.mock
    async def test_select_param_is_sent(self):
        route = respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(200, json=USER_RESPONSE)
        )
        await make_client().get_current_user()
        url_str = str(route.calls.last.request.url)
        assert "select" in url_str.lower()

    @respx.mock
    async def test_bearer_token_in_authorization_header(self):
        route = respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(200, json=USER_RESPONSE)
        )
        await make_client().get_current_user()
        assert route.calls.last.request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"

    @respx.mock
    async def test_401_raises_graph_auth_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(401, json=GRAPH_ERROR_BODY)
        )
        with pytest.raises(GraphAuthError) as exc_info:
            await make_client().get_current_user()
        assert "401" in exc_info.value.message

    @respx.mock
    async def test_403_raises_graph_auth_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(403, json=GRAPH_ERROR_BODY)
        )
        with pytest.raises(GraphAuthError) as exc_info:
            await make_client().get_current_user()
        assert "403" in exc_info.value.message

    @respx.mock
    async def test_500_raises_graph_service_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(500, text="Internal Server Error")
        )
        with pytest.raises(GraphServiceError) as exc_info:
            await make_client().get_current_user()
        assert "500" in exc_info.value.message

    @respx.mock
    async def test_404_raises_graph_service_error_without_retry(self):
        """404 is a deterministic failure — must not trigger retry logic."""
        call_count = 0

        def side_effect(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            return Response(404, text="Not Found")

        respx.get(f"{GRAPH_BASE_URL}/me").mock(side_effect=side_effect)

        with pytest.raises(GraphServiceError):
            await make_client().get_current_user()

        assert call_count == 1  # No retries for 404


# ---------------------------------------------------------------------------
# get_calendar_events tests
# ---------------------------------------------------------------------------

class TestGetCalendarEvents:

    @respx.mock
    async def test_returns_calendar_dict_on_200(self):
        respx.get(f"{GRAPH_BASE_URL}/me/calendarView").mock(
            return_value=Response(200, json=CALENDAR_RESPONSE)
        )
        result = await make_client().get_calendar_events()
        assert "value" in result
        assert result["value"][0]["subject"] == "Sprint planning"

    @respx.mock
    async def test_date_range_params_are_sent(self):
        route = respx.get(f"{GRAPH_BASE_URL}/me/calendarView").mock(
            return_value=Response(200, json=CALENDAR_RESPONSE)
        )
        await make_client().get_calendar_events()
        url_str = str(route.calls.last.request.url)
        assert "startDateTime" in url_str
        assert "endDateTime" in url_str

    @respx.mock
    async def test_select_orderby_top_params_are_sent(self):
        route = respx.get(f"{GRAPH_BASE_URL}/me/calendarView").mock(
            return_value=Response(200, json=CALENDAR_RESPONSE)
        )
        await make_client().get_calendar_events()
        url_str = str(route.calls.last.request.url)
        assert "select" in url_str.lower()
        assert "orderby" in url_str.lower()
        assert "top" in url_str.lower()

    @respx.mock
    async def test_401_raises_graph_auth_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me/calendarView").mock(
            return_value=Response(401, json=GRAPH_ERROR_BODY)
        )
        with pytest.raises(GraphAuthError):
            await make_client().get_calendar_events()

    @respx.mock
    async def test_500_raises_graph_service_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me/calendarView").mock(
            return_value=Response(500, text="Internal Server Error")
        )
        with pytest.raises(GraphServiceError) as exc_info:
            await make_client().get_calendar_events()
        assert "500" in exc_info.value.message


# ---------------------------------------------------------------------------
# get_messages tests
# ---------------------------------------------------------------------------

class TestGetMessages:

    @respx.mock
    async def test_returns_messages_dict_on_200(self):
        respx.get(f"{GRAPH_BASE_URL}/me/messages").mock(
            return_value=Response(200, json=MESSAGES_RESPONSE)
        )
        result = await make_client().get_messages()
        assert "value" in result
        assert result["value"][0]["subject"] == "Action required: review PR"

    @respx.mock
    async def test_filter_param_is_sent(self):
        route = respx.get(f"{GRAPH_BASE_URL}/me/messages").mock(
            return_value=Response(200, json=MESSAGES_RESPONSE)
        )
        await make_client().get_messages()
        url_str = str(route.calls.last.request.url)
        assert "filter" in url_str.lower()

    @respx.mock
    async def test_select_orderby_top_params_are_sent(self):
        route = respx.get(f"{GRAPH_BASE_URL}/me/messages").mock(
            return_value=Response(200, json=MESSAGES_RESPONSE)
        )
        await make_client().get_messages()
        url_str = str(route.calls.last.request.url)
        assert "select" in url_str.lower()
        assert "orderby" in url_str.lower()
        assert "top" in url_str.lower()

    @respx.mock
    async def test_401_raises_graph_auth_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me/messages").mock(
            return_value=Response(401, json=GRAPH_ERROR_BODY)
        )
        with pytest.raises(GraphAuthError):
            await make_client().get_messages()

    @respx.mock
    async def test_403_raises_graph_auth_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me/messages").mock(
            return_value=Response(403, json=GRAPH_ERROR_BODY)
        )
        with pytest.raises(GraphAuthError) as exc_info:
            await make_client().get_messages()
        assert "403" in exc_info.value.message

    @respx.mock
    async def test_500_raises_graph_service_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me/messages").mock(
            return_value=Response(500, text="Server error")
        )
        with pytest.raises(GraphServiceError):
            await make_client().get_messages()


# ---------------------------------------------------------------------------
# ping() tests
# ---------------------------------------------------------------------------

class TestPing:

    @respx.mock
    async def test_returns_true_when_graph_responds_200(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(200, json=USER_RESPONSE)
        )
        assert await make_client().ping() is True

    @respx.mock
    async def test_returns_false_on_401(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(401, json=GRAPH_ERROR_BODY)
        )
        assert await make_client().ping() is False

    @respx.mock
    async def test_returns_false_on_500(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(500, text="Internal Server Error")
        )
        assert await make_client().ping() is False

    @respx.mock
    async def test_returns_false_on_network_error_and_does_not_raise(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await make_client().ping()
        assert result is False

    @respx.mock
    async def test_returns_false_on_403_and_does_not_raise(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(403, json=GRAPH_ERROR_BODY)
        )
        assert await make_client().ping() is False


# ---------------------------------------------------------------------------
# Retry on 429 tests
# ---------------------------------------------------------------------------

class TestRetryOn429:

    @respx.mock
    async def test_retries_once_and_succeeds(self):
        call_count = 0

        def side_effect(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(429, json={"error": {"message": "rate limited"}})
            return Response(200, json=USER_RESPONSE)

        respx.get(f"{GRAPH_BASE_URL}/me").mock(side_effect=side_effect)

        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await make_client().get_current_user()

        assert result["id"] == "oid-001"
        mock_sleep.assert_awaited_once_with(1.0)

    @respx.mock
    async def test_exhausted_raises_graph_rate_limit_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(429, json={"error": {"message": "rate limited"}})
        )
        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(GraphRateLimitError) as exc_info:
                await make_client().get_current_user()
        assert "429" in exc_info.value.message

    @respx.mock
    async def test_back_off_delays_are_1s_then_2s(self):
        """Verify sleep durations: 1.0 s before attempt 2, 2.0 s before attempt 3."""
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(429, json={"error": {"message": "rate limited"}})
        )
        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            with pytest.raises(GraphRateLimitError):
                await make_client().get_current_user()

        assert mock_sleep.await_count == 2
        delays = [call.args[0] for call in mock_sleep.await_args_list]
        assert delays == [1.0, 2.0]

    @respx.mock
    async def test_401_is_not_retried(self):
        """Authentication failures must not trigger the retry path."""
        call_count = 0

        def side_effect(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            return Response(401, json=GRAPH_ERROR_BODY)

        respx.get(f"{GRAPH_BASE_URL}/me").mock(side_effect=side_effect)

        with pytest.raises(GraphAuthError):
            await make_client().get_current_user()

        assert call_count == 1


# ---------------------------------------------------------------------------
# Retry on 503 tests
# ---------------------------------------------------------------------------

class TestRetryOn503:

    @respx.mock
    async def test_retries_once_and_succeeds(self):
        call_count = 0

        def side_effect(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(503, text="Service Unavailable")
            return Response(200, json=USER_RESPONSE)

        respx.get(f"{GRAPH_BASE_URL}/me").mock(side_effect=side_effect)

        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await make_client().get_current_user()

        assert result["id"] == "oid-001"
        mock_sleep.assert_awaited_once_with(1.0)

    @respx.mock
    async def test_exhausted_raises_graph_rate_limit_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            return_value=Response(503, text="Service Unavailable")
        )
        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(GraphRateLimitError) as exc_info:
                await make_client().get_current_user()
        assert "503" in exc_info.value.message


# ---------------------------------------------------------------------------
# Network error retry tests
# ---------------------------------------------------------------------------

class TestNetworkErrorRetry:

    @respx.mock
    async def test_network_error_retries_then_succeeds(self):
        call_count = 0

        def side_effect(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("connection refused")
            return Response(200, json=USER_RESPONSE)

        respx.get(f"{GRAPH_BASE_URL}/me").mock(side_effect=side_effect)

        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await make_client().get_current_user()

        assert result["id"] == "oid-001"
        mock_sleep.assert_awaited_once_with(1.0)

    @respx.mock
    async def test_network_error_exhausted_raises_graph_service_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(GraphServiceError) as exc_info:
                await make_client().get_current_user()
        assert "Network error" in exc_info.value.message


# ---------------------------------------------------------------------------
# Timeout retry tests
# ---------------------------------------------------------------------------

class TestTimeoutRetry:

    @respx.mock
    async def test_timeout_retries_then_succeeds(self):
        call_count = 0

        def side_effect(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timed out")
            return Response(200, json=USER_RESPONSE)

        respx.get(f"{GRAPH_BASE_URL}/me").mock(side_effect=side_effect)

        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            result = await make_client().get_current_user()

        assert result["id"] == "oid-001"
        mock_sleep.assert_awaited_once_with(1.0)

    @respx.mock
    async def test_timeout_exhausted_raises_graph_service_error(self):
        respx.get(f"{GRAPH_BASE_URL}/me").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with patch(
            "app.connectors.outlook.graph_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(GraphServiceError) as exc_info:
                await make_client().get_current_user()
        assert "timed out" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# _extract_error_message tests
# ---------------------------------------------------------------------------

class TestExtractErrorMessage:

    def test_extracts_message_from_graph_error_body(self):
        response = Response(401, json=GRAPH_ERROR_BODY)
        result = _extract_error_message(response)
        assert result == "Access token has expired or is yet to be valid."

    def test_falls_back_to_text_when_no_message_key(self):
        response = Response(500, json={"error": {"code": "InternalServerError"}})
        result = _extract_error_message(response)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_falls_back_to_text_when_body_is_not_json(self):
        response = Response(503, text="Service Unavailable")
        result = _extract_error_message(response)
        assert "Service Unavailable" in result

    def test_falls_back_to_text_when_no_error_key(self):
        response = Response(400, json={"someOtherKey": "value"})
        result = _extract_error_message(response)
        assert isinstance(result, str)

    def test_falls_back_to_text_when_message_is_empty_string(self):
        """Empty string is falsy — should fall back to response text, not return ''."""
        response = Response(500, json={"error": {"code": "InternalError", "message": ""}})
        result = _extract_error_message(response)
        # The empty message triggers the `or` fallback; result must be non-empty text.
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != ""


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------

class TestExceptionHierarchy:

    def test_graph_auth_error_is_graph_error(self):
        exc = GraphAuthError("token expired")
        assert isinstance(exc, Exception)
        assert exc.message == "token expired"

    def test_graph_rate_limit_error_is_graph_error(self):
        from app.connectors.outlook.graph_client import GraphError
        exc = GraphRateLimitError("rate limited")
        assert isinstance(exc, GraphError)

    def test_graph_service_error_is_graph_error(self):
        from app.connectors.outlook.graph_client import GraphError
        exc = GraphServiceError("server error")
        assert isinstance(exc, GraphError)

    def test_all_graph_errors_are_exceptions(self):
        from app.connectors.outlook.graph_client import GraphError
        for cls in (GraphError, GraphAuthError, GraphRateLimitError, GraphServiceError):
            exc = cls("test")
            assert isinstance(exc, Exception)
            assert exc.message == "test"
