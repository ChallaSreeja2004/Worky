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
import base64
import json
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
            # Request UTC datetimes from Graph calendarView.
            # Without this header Graph returns times in the calendar's
            # configured timezone (e.g. "India Standard Time") as a bare
            # datetime string with no UTC offset — which JavaScript's
            # Date constructor treats as local time, breaking epoch
            # comparisons in non-UTC browsers.  "UTC" guarantees the Z
            # suffix so new Date() parses the epoch correctly everywhere.
            "Prefer": 'outlook.timezone="UTC"',
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
                &$top=25

        Note: ``$orderby`` is intentionally omitted when ``$filter`` is present.
        Combining ``$filter`` and ``$orderby`` on ``/me/messages`` is not
        supported by personal Outlook.com (MSA) mailboxes and returns 501 or
        400.  The result set is already sorted by ``receivedDateTime desc``
        by default for Outlook.com; Exchange Online callers may see a different
        default sort order, but all callers use ``receivedDateTime`` from each
        message object anyway — explicit ordering is not required.

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

        # Log outgoing request details once, before the retry loop.
        # The bearer token is never logged in full — only structural metadata
        # (length, first/last 10 chars) and JWT claims are emitted.
        _log_outgoing_request(self._access_token, url)

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
                    _log_graph_auth_failure(response, path, url)
                    detail = _extract_error_detail(response)
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
                detail = _extract_error_detail(response)
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

def _decode_jwt_claims(token: str) -> dict:
    """
    Decode the payload of a JWT without verifying the signature.

    Microsoft access tokens are JWTs (three dot-separated base64url segments).
    We only need the payload claims for diagnostic logging — signature
    verification is Microsoft's server-side responsibility.

    Returns a dict of claims, or a dict with a single ``_error`` key if the
    token is not a valid JWT.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {"_error": f"not a JWT — {len(parts)} segment(s)"}

        # JWT base64url payload may omit padding — restore it.
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(payload_bytes)
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"decode failed: {exc}"}


def _log_outgoing_request(access_token: str, url: str) -> None:
    """
    Log structural metadata about the outgoing Graph request.

    Emitted once per ``_get()`` call, before the HTTP request is sent.
    Used to confirm:
      • The Authorization header carries "Bearer <token>" (not a raw secret)
      • The token is a well-formed JWT (not an encrypted refresh token or id_token)
      • The JWT audience (``aud``) targets Microsoft Graph
      • The JWT scopes (``scp``) include the expected delegated permissions
      • The JWT has not already expired (``exp``)
      • The token length is plausible (Graph access tokens are 1 500–2 000 chars)

    Security: only token length and the first/last 10 characters are logged.
    The full token value is NEVER written to logs.
    """
    token_len = len(access_token)

    # First and last 10 characters give enough entropy to confirm whether the
    # same token is reused across requests without exposing the full value.
    if token_len >= 20:
        token_preview = f"{access_token[:10]}...{access_token[-10:]}"
    elif token_len > 0:
        token_preview = f"{access_token[:5]}...<{token_len} chars total>"
    else:
        token_preview = "<empty>"

    # Determine the authorization scheme (should always be "Bearer").
    scheme = "Bearer" if access_token else "<missing>"

    logger.info(
        "GraphAPIClient: outgoing request\n"
        "  url             : %s\n"
        "  auth scheme     : %s <redacted>\n"
        "  token length    : %d chars\n"
        "  token preview   : %s",
        url, scheme, token_len, token_preview,
    )

    # Decode and log the JWT payload claims.  This is the most reliable way
    # to confirm exactly which token is being sent and whether it is valid
    # for Graph (correct audience, unexpired, correct scopes).
    claims = _decode_jwt_claims(access_token)

    if "_error" in claims:
        logger.error(
            "GraphAPIClient: token is NOT a valid JWT — %s\n"
            "  Likely cause: the encrypted refresh_token or the raw client_secret\n"
            "  is being used instead of the access_token.",
            claims["_error"],
        )
        return

    # Extract the diagnostic claims.
    aud  = claims.get("aud",  "<missing>")
    iss  = claims.get("iss",  "<missing>")
    scp  = claims.get("scp",  claims.get("roles", "<missing>"))  # delegated vs app-only
    tid  = claims.get("tid",  "<missing>")
    upn  = claims.get("upn",  claims.get("preferred_username", "<missing>"))
    nbf  = claims.get("nbf",  None)
    exp  = claims.get("exp",  None)

    # Convert numeric epoch timestamps to readable UTC strings.
    def _ts(epoch: int | None) -> str:
        if epoch is None:
            return "<missing>"
        try:
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            return str(epoch)

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    is_expired = (exp is not None) and (now_epoch >= exp)
    expiry_note = " *** EXPIRED ***" if is_expired else ""

    # Graph access tokens must have aud == "https://graph.microsoft.com" or
    # "00000003-0000-0000-c000-000000000000" (Graph's app ID).
    graph_audiences = {
        "https://graph.microsoft.com",
        "00000003-0000-0000-c000-000000000000",
    }
    wrong_audience = str(aud) not in graph_audiences

    logger.info(
        "GraphAPIClient: JWT claims\n"
        "  aud  : %s%s\n"
        "  iss  : %s\n"
        "  scp  : %s\n"
        "  tid  : %s\n"
        "  upn  : %s\n"
        "  nbf  : %s\n"
        "  exp  : %s%s",
        aud,
        "  *** WRONG AUDIENCE — not a Graph token ***" if wrong_audience else "",
        iss,
        scp,
        tid,
        upn,
        _ts(nbf),
        _ts(exp),
        expiry_note,
    )

    if wrong_audience:
        logger.error(
            "GraphAPIClient: token audience '%s' is not Microsoft Graph.\n"
            "  Expected: 'https://graph.microsoft.com' or "
            "'00000003-0000-0000-c000-000000000000'.\n"
            "  This token cannot be used to call Graph endpoints.\n"
            "  Root cause candidates:\n"
            "    1. The scope list sent to /authorize did not include a Graph\n"
            "       delegated scope (e.g. 'User.Read'). OIDC-only scopes\n"
            "       (openid/profile/email) produce tokens for the OIDC audience,\n"
            "       not for Graph.\n"
            "    2. The id_token (not the access_token) is being stored or\n"
            "       retrieved from the repository.",
            aud,
        )

    if is_expired:
        logger.error(
            "GraphAPIClient: token expired at %s (now %s).\n"
            "  AuthService.get_valid_token() should have refreshed this token.\n"
            "  Check that the system clock is not skewed and that the token\n"
            "  expiry buffer (TOKEN_REFRESH_BUFFER_MINUTES) is applied correctly.",
            _ts(exp),
            _ts(now_epoch),
        )


def _extract_error_detail(response: httpx.Response) -> str:
    """
    Return a single-line summary of a Graph error response for use in
    exception messages.

    Graph error responses follow the schema:
        {"error": {"code": "...", "message": "..."}}

    Returns ``"<code>: <message>"`` when both fields are present, falls back
    to ``"<code>"`` if message is absent, and falls back to
    ``response.text[:300]`` when the body cannot be parsed as JSON.
    """
    try:
        body = response.json()
        error = body.get("error", {})
        code = error.get("code", "")
        message = error.get("message", "")
        if code and message:
            return f"{code}: {message}"
        if code:
            return code
        return message or response.text[:300]
    except Exception:  # noqa: BLE001
        return response.text[:300]


def _log_graph_auth_failure(
    response: httpx.Response,
    path: str,
    url: str,
) -> None:
    """
    Emit a structured ERROR log entry for every 401/403 response from Graph.

    Logs all fields needed to diagnose the exact rejection reason without
    requiring a separate curl run:

      - HTTP status code
      - Full request URL (including query parameters)
      - error.code   — e.g. "InvalidAuthenticationToken", "Forbidden"
      - error.code innerError.code  — e.g. "InvalidAudience", "TokenExpired"
      - error.message — human-readable explanation from Microsoft
      - WWW-Authenticate header — Bearer realm, error, error_description
      - First 1 000 chars of raw response body (for cases where JSON parse fails)

    The Authorization header value is intentionally NOT logged — it contains
    the raw bearer token and must never appear in log files.
    """
    status = response.status_code
    www_auth = response.headers.get("WWW-Authenticate", "<not present>")

    # Attempt to parse the Graph error body.
    error_code = "<unknown>"
    inner_code  = "<none>"
    error_msg   = "<none>"
    raw_body    = response.text[:1000]

    try:
        body = response.json()
        err = body.get("error", {})
        error_code = err.get("code", "<unknown>")
        error_msg  = err.get("message", "<none>")
        inner      = err.get("innerError", {})
        inner_code = inner.get("code", "<none>")
    except Exception:  # noqa: BLE001
        pass  # raw_body already captured above

    logger.error(
        "GraphAPIClient: Graph auth failure\n"
        "  status          : %d\n"
        "  path            : %s\n"
        "  full url        : %s\n"
        "  error.code      : %s\n"
        "  innerError.code : %s\n"
        "  error.message   : %s\n"
        "  WWW-Authenticate: %s\n"
        "  raw body        : %s",
        status, path, url,
        error_code, inner_code, error_msg,
        www_auth,
        raw_body,
    )

    # Log a targeted hint for the most common root causes so the reader does
    # not need to look up Microsoft's error code documentation.
    _hint = _auth_failure_hint(error_code, inner_code, www_auth)
    if _hint:
        logger.error("GraphAPIClient: diagnosis hint — %s", _hint)


def _auth_failure_hint(
    error_code: str,
    inner_code: str,
    www_auth: str,
) -> str:
    """
    Return a plain-English hint for the most common Graph 401/403 root causes.

    Returns an empty string when no hint can be derived.
    """
    combined = f"{error_code} {inner_code} {www_auth}".lower()

    if "invalidauthenticationtoken" in combined:
        if "invalidaudience" in combined:
            return (
                "InvalidAudience: the access token was issued for a different "
                "resource (audience). The token obtained via the /token endpoint "
                "may target the wrong API — ensure the scope includes "
                "'https://graph.microsoft.com/.default' or a delegated Graph scope "
                "such as 'User.Read'. Tokens scoped only to 'openid/profile/email' "
                "are OIDC tokens and cannot call Graph."
            )
        if "expiredtoken" in combined or "lifetime" in combined:
            return (
                "ExpiredToken: the access token has expired. "
                "AuthService.get_valid_token() should refresh it automatically. "
                "Check that the token stored after /auth/callback is not already "
                "near expiry and that the system clock is not skewed."
            )
        return (
            "InvalidAuthenticationToken: the token is malformed, truncated, or "
            "was issued for a different tenant. Verify the token is the raw "
            "access_token string returned by Microsoft (not the id_token or "
            "the encrypted refresh_token)."
        )

    if "insufficient_claims" in combined or "insufficientscopes" in combined:
        return (
            "Insufficient scopes: the token was issued without the required "
            "delegated permissions. Re-authenticate with the full scope list: "
            "openid profile email User.Read Calendars.Read Mail.Read offline_access."
        )

    if "forbidden" in combined or error_code.lower() == "403":
        return (
            "Forbidden (403): the token is valid but the application does not "
            "have the required Microsoft Graph permissions. Check the app "
            "registration in Azure Portal → API permissions and ensure "
            "Calendars.Read and Mail.Read are granted."
        )

    return ""


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
