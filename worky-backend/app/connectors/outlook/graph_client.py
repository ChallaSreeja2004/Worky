"""
app/connectors/outlook/graph_client.py
=======================================
GraphAPIClient — the single HTTP abstraction for Microsoft Graph API calls.

RESPONSIBILITIES
----------------
  • Attach the Authorization: Bearer <token> header on every request.
  • Centralise all Microsoft Graph HTTP communication for the Outlook connector.
  • Retry transient failures (HTTP 429, HTTP 503) with exponential back-off.
  • Raise typed, Graph-specific exceptions so callers can react precisely.
  • Return raw Microsoft Graph JSON — no normalisation, no transformation.

WHAT THIS CLIENT DOES NOT DO
------------------------------
  • It does NOT refresh tokens.  A valid access_token must be provided by
    the caller (AuthService.get_valid_token()).
  • It does NOT know about AuthService, TokenRepository, or their internals.
  • It does NOT know about ConnectorResult, WorkContext, or IBM Bob.
  • It does NOT normalise or interpret Microsoft Graph responses.
  • It does NOT cache responses.
  • It does NOT contain business logic.

RETRY POLICY
------------
Only HTTP 429 (Too Many Requests) and HTTP 503 (Service Unavailable) trigger
retries — these are transient load conditions, not deterministic failures.

  Attempt 1 → failure → wait 1 s
  Attempt 2 → failure → wait 2 s
  Attempt 3 → failure → raise GraphRateLimitError  (429 / 503)
                       raise GraphServiceError      (timeout / network)

All other non-2xx responses (400, 401, 403, 404, 500, …) are raised
immediately without retrying.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • httpx

It must NOT import from:
  • app.auth
  • app.config
  • app.connectors.base
  • app.connectors.models
  • app.context_builder
  • any other app module
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"

_MAX_RETRIES: int = 3
_RETRY_BACK_OFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 503})


# ---------------------------------------------------------------------------
# GraphAPIClient
# ---------------------------------------------------------------------------

class GraphAPIClient:
    """
    Authenticated, async HTTP client for Microsoft Graph API v1.0.

    Designed to be instantiated once per connector execution cycle and
    discarded afterwards.  It is not a long-lived singleton — the bearer
    token it carries has a finite lifetime and is scoped to a single user.

    Parameters
    ----------
    access_token : str
        A valid, unexpired Microsoft Graph bearer token.  Obtain one via
        AuthService.get_valid_token() before constructing this client.
    timeout : float
        Per-request timeout in seconds.  Defaults to 20.0 s — generous
        enough for Graph's occasional slow responses while still failing
        fast during health checks.
    """

    def __init__(self, access_token: str, timeout: float = 20.0) -> None:
        self._access_token = access_token
        self._timeout = timeout
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_current_user(self) -> dict[str, Any]:
        """
        Fetch the signed-in user's profile from /me.

        Graph endpoint:
            GET /v1.0/me
                ?$select=id,displayName,mail,userPrincipalName

        Required scope: User.Read

        Returns
        -------
        dict
            Raw Graph JSON for the user resource.  Relevant fields:
              id                — Azure AD object ID (stable user identifier)
              displayName       — full name
              mail              — primary SMTP address
              userPrincipalName — UPN / login address
        """
        return await self._get(
            "/me",
            params={"$select": "id,displayName,mail,userPrincipalName"},
        )

    async def get_calendar_events(self) -> dict[str, Any]:
        """
        Fetch today's calendar events from the user's default calendar.

        Graph endpoint:
            GET /v1.0/me/calendarView
                ?startDateTime=<today 00:00 UTC>
                &endDateTime=<today 23:59:59 UTC>
                &$select=id,subject,start,end,location,organizer,
                         isAllDay,isCancelled,onlineMeeting,bodyPreview
                &$orderby=start/dateTime asc
                &$top=20

        Required scope: Calendars.Read

        Returns
        -------
        dict
            Raw Graph JSON with a ``value`` list of calendar event objects.
        """
        today = date.today()
        start = (
            datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        end = (
            datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

        return await self._get(
            "/me/calendarView",
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$select": (
                    "id,subject,start,end,location,organizer,"
                    "isAllDay,isCancelled,onlineMeeting,bodyPreview"
                ),
                "$orderby": "start/dateTime asc",
                "$top": "20",
            },
        )

    async def get_messages(self) -> dict[str, Any]:
        """
        Fetch unread emails and high-importance emails from the user's inbox.

        Graph endpoint:
            GET /v1.0/me/messages
                ?$filter=isRead eq false or importance eq 'high'
                &$select=id,subject,from,receivedDateTime,
                         isRead,importance,bodyPreview,hasAttachments
                &$orderby=receivedDateTime desc
                &$top=25

        Required scope: Mail.Read

        Returns
        -------
        dict
            Raw Graph JSON with a ``value`` list of message objects.
        """
        return await self._get(
            "/me/messages",
            params={
                "$filter": "isRead eq false or importance eq 'high'",
                "$select": (
                    "id,subject,from,receivedDateTime,"
                    "isRead,importance,bodyPreview,hasAttachments"
                ),
                "$orderby": "receivedDateTime desc",
                "$top": "25",
            },
        )

    async def ping(self) -> bool:
        """
        Verify that the Microsoft Graph API is reachable and the token is valid.

        Makes a lightweight /me request and returns True on success.  Returns
        False on any failure without raising — this method is used by
        OutlookConnector.health_check() and must never propagate exceptions.

        Returns
        -------
        bool
            True  — Graph responded with HTTP 200.
            False — Any error occurred (network, auth, timeout, …).
        """
        try:
            await self.get_current_user()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("GraphAPIClient.ping: health check failed — %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal HTTP layer
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GET request against the Graph API with retry logic.

        Parameters
        ----------
        path : str
            Graph API path relative to GRAPH_BASE_URL, e.g. ``/me/messages``.
        params : dict, optional
            Query parameters appended to the URL.

        Returns
        -------
        dict
            Parsed JSON response body.

        Raises
        ------
        GraphAuthError
            On HTTP 401 Unauthorized or 403 Forbidden.
        GraphRateLimitError
            On HTTP 429 or 503 after all retry attempts are exhausted.
        GraphServiceError
            On any other non-2xx response or on an unrecoverable network
            or timeout failure after all retry attempts are exhausted.
        """
        url = f"{GRAPH_BASE_URL}{path}"

        # The client is constructed once outside the retry loop so that the
        # underlying TCP connection pool is reused across attempts.  Creating
        # a new AsyncClient on every iteration would open a fresh connection
        # per retry, defeating keep-alive entirely.
        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=self._timeout,
        ) as client:
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    response = await client.get(url, params=params)

                except httpx.RequestError as exc:
                    # Covers both TimeoutException (subclass) and all other
                    # network-level failures (DNS, connection refused, …).
                    # Both are retried on the first two attempts with the same
                    # back-off policy; only the final error message differs.
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACK_OFF_SECONDS[attempt - 1]
                        logger.warning(
                            "GraphAPIClient: %s on %s (attempt %d/%d) — "
                            "retrying in %.1f s",
                            type(exc).__name__, path, attempt, _MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    if isinstance(exc, httpx.TimeoutException):
                        raise GraphServiceError(
                            f"Request to Graph API {path!r} timed out after "
                            f"{_MAX_RETRIES} attempts."
                        ) from exc
                    raise GraphServiceError(
                        f"Network error calling Graph API {path!r}: {exc}"
                    ) from exc

                # ----------------------------------------------------------
                # Response handling
                # ----------------------------------------------------------

                if response.status_code == 200:
                    return response.json()

                if response.status_code in (401, 403):
                    detail = _extract_error_message(response)
                    logger.error(
                        "GraphAPIClient: auth failure %d on %s — %s",
                        response.status_code, path, detail,
                    )
                    raise GraphAuthError(
                        f"Graph API returned {response.status_code} on {path!r}: "
                        f"{detail}"
                    )

                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACK_OFF_SECONDS[attempt - 1]
                        logger.warning(
                            "GraphAPIClient: %d on %s (attempt %d/%d) — "
                            "retrying in %.1f s",
                            response.status_code, path, attempt, _MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    # All retries exhausted.
                    raise GraphRateLimitError(
                        f"Graph API returned {response.status_code} on {path!r} "
                        f"after {_MAX_RETRIES} attempts."
                    )

                # Any other non-2xx response — fail immediately, no retry.
                detail = _extract_error_message(response)
                logger.error(
                    "GraphAPIClient: unexpected %d on %s — %s",
                    response.status_code, path, detail,
                )
                raise GraphServiceError(
                    f"Graph API returned {response.status_code} on {path!r}: "
                    f"{detail}"
                )

        # Unreachable — the loop always returns or raises.
        raise GraphServiceError(  # pragma: no cover
            f"Graph API call to {path!r} failed after {_MAX_RETRIES} attempts."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_error_message(response: httpx.Response) -> str:
    """
    Extract a human-readable error message from a Graph error response body.

    Graph error responses follow the schema:
        {"error": {"code": "...", "message": "..."}}

    Falls back to ``response.text[:200]`` in two cases:
      • The body cannot be parsed as JSON.
      • The ``message`` field is absent or is an empty string.
    """
    try:
        body = response.json()
        error = body.get("error", {})
        return error.get("message") or response.text[:200]
    except Exception:  # noqa: BLE001
        return response.text[:200]


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class GraphError(Exception):
    """
    Base class for all Microsoft Graph API errors raised by GraphAPIClient.

    All Graph-specific exceptions inherit from this class so callers can
    catch ``GraphError`` in a single clause when they do not need to
    distinguish between failure modes.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class GraphAuthError(GraphError):
    """
    Raised on HTTP 401 Unauthorized or 403 Forbidden from Graph API.

    Indicates the bearer token is invalid, expired, or lacks a required
    permission scope.  The caller should trigger a token refresh or prompt
    the user to re-authenticate via AuthService.
    """


class GraphRateLimitError(GraphError):
    """
    Raised on HTTP 429 Too Many Requests or 503 Service Unavailable after
    all retry attempts are exhausted.

    The caller (OutlookConnector) should surface this as a PARTIAL result
    so the Context Builder can still include data from other connectors.
    """


class GraphServiceError(GraphError):
    """
    Raised on any other non-2xx response, network error, or timeout that
    is not covered by GraphAuthError or GraphRateLimitError.

    Covers: 400 Bad Request, 404 Not Found, 500 Internal Server Error,
    502 Bad Gateway, network timeouts, DNS failures, etc.
    """
