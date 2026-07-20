"""
app/bob/service.py
===================
BobService — abstract interface and IBM Bob concrete implementation.

RESPONSIBILITIES
----------------
  • Define the single BobService interface that the rest of the codebase
    depends on.  No other layer imports IBMBobService directly — they
    depend only on BobService (Dependency Inversion Principle).

  • IBMBobService: send a WorkContext to the IBM Bob reasoning API, validate
    the response, and return a structured RecommendationSet.

WHAT THIS MODULE DOES NOT DO
------------------------------
  • It does NOT know about Outlook, Slack, GitHub, or any connector.
  • It does NOT know about the recommendation cache or scheduler.
  • It does NOT know about routers or HTTP response formats.
  • It does NOT refresh tokens or manage authentication.
  • It does NOT schedule periodic calls — that is the Recommendation
    Service's responsibility (Phase 11).

IBM BOB API SHAPE (expected by IBMBobService)
---------------------------------------------
  POST {BOB_API_URL}/analyze
  Headers:
    Authorization: ApiKey <BOB_API_KEY>
    Content-Type: application/json
  Body:
    BobRequest.model_dump(mode="json")

  Response (200 OK):
    {
      "recommendations": [
        {
          "priority": 1,
          "category": "email",
          "title": "...",
          "description": "...",
          "action_url": "...",
          "source": "outlook"
        }
      ],
      "model_version": "bob-1.0"
    }

  Any non-200 response or missing required field raises BobServiceError.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • httpx
  • app.bob.models
  • app.bob.settings
  • app.context_builder.models  (WorkContext — the only input type)

It must NOT import from:
  • app.connectors.*
  • app.auth
  • app.config
  • app.recommendations
  • fastapi
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from app.bob.models import BobRequest, Recommendation, RecommendationSet
from app.bob.settings import get_bob_settings
from app.context_builder.models import WorkContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class BobService(ABC):
    """
    Abstract interface for the IBM Bob reasoning service.

    The Recommendation Service (Phase 11) and any future caller depends
    on this interface, never on a concrete implementation.  This is the
    Dependency Inversion Principle applied to AI integration.

    Switching from MockBobService (development) to IBMBobService (production)
    is a single DI configuration change in app/bob/dependencies.py.  Zero
    changes are required in any caller.

    Interface contract
    ------------------
    ::

        recommendation_set = await bob_service.analyze(work_context)

    Bob has one input (WorkContext) and one output (RecommendationSet).
    It never:
      • Calls connectors directly.
      • Accesses the token repository.
      • Knows which enterprise applications are active.
    """

    @abstractmethod
    async def analyze(self, work_context: WorkContext) -> RecommendationSet:
        """
        Analyze a WorkContext and return a prioritised RecommendationSet.

        Parameters
        ----------
        work_context : WorkContext
            The complete, point-in-time snapshot of the user's enterprise
            environment assembled by the ContextBuilder.  This is the ONLY
            data that Bob receives.

        Returns
        -------
        RecommendationSet
            A fully populated set of prioritised recommendations for the user.
            The caller should treat every returned RecommendationSet as valid
            even if it contains an empty recommendations list — an empty set
            is a legitimate outcome when no action items are present.

        Raises
        ------
        BobServiceError
            On any unrecoverable failure (network error, invalid response,
            configuration error).  Callers should catch BobServiceError and
            decide how to surface the failure — typically by storing the
            previous cached result and logging the error.
        """
        ...


# ---------------------------------------------------------------------------
# IBM Bob concrete implementation
# ---------------------------------------------------------------------------

class IBMBobService(BobService):
    """
    Concrete BobService that calls the IBM Bob REST API.

    Constructs a BobRequest from the WorkContext, POSTs it to Bob's
    /analyze endpoint, validates the response, and returns a
    RecommendationSet.

    Parameters
    ----------
    api_url : str
        Base URL of the IBM Bob API.  Typically injected from BobSettings.
        Must NOT have a trailing slash.
    api_key : str
        API key for authenticating with IBM Bob.  Never logged.
    timeout : float
        Per-request timeout in seconds.

    Usage (via DI, not direct instantiation):
    ::

        # In app/bob/dependencies.py:
        bob_service = IBMBobService(
            api_url=settings.bob_api_url,
            api_key=settings.bob_api_key,
            timeout=settings.bob_timeout_seconds,
        )
    """

    # The Bob API endpoint path relative to api_url.
    _ANALYZE_PATH: str = "/analyze"

    # Version tag included in request metadata.
    _MODEL_VERSION: str = "ibm-bob-v1"

    def __init__(self, api_url: str, api_key: str, timeout: float = 30.0) -> None:
        if not api_url:
            raise BobConfigError(
                "BOB_API_URL must be set to use IBMBobService. "
                "Use MockBobService for development."
            )
        if not api_key:
            raise BobConfigError(
                "BOB_API_KEY must be set to use IBMBobService. "
                "Use MockBobService for development."
            )

        self._api_url = api_url.rstrip("/")
        self._timeout = timeout
        # api_key is held in an attribute that is never logged or included
        # in exception messages.
        self._headers: dict[str, str] = {
            "Authorization": f"ApiKey {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def analyze(self, work_context: WorkContext) -> RecommendationSet:
        """
        Send the WorkContext to IBM Bob and return a RecommendationSet.

        Builds a BobRequest, serialises it to JSON, POSTs to Bob's /analyze
        endpoint, and parses the response into a RecommendationSet.

        Raises
        ------
        BobServiceError
            On network failures, timeouts, non-200 responses, or if the
            response body does not contain the expected shape.
        """
        request_id = str(uuid.uuid4())
        bob_request = BobRequest(
            context=work_context,
            request_id=request_id,
        )

        endpoint = f"{self._api_url}{self._ANALYZE_PATH}"

        logger.info(
            "IBMBobService: calling Bob API — user_id=%s request_id=%s "
            "active_sources=%s",
            work_context.user_id,
            request_id,
            work_context.active_sources,
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    endpoint,
                    json=bob_request.model_dump(mode="json"),
                    headers=self._headers,
                )
        except httpx.TimeoutException as exc:
            logger.error(
                "IBMBobService: request timed out — user_id=%s request_id=%s",
                work_context.user_id,
                request_id,
            )
            raise BobTimeoutError(
                f"IBM Bob API timed out after {self._timeout}s "
                f"(request_id={request_id})."
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "IBMBobService: network error — user_id=%s request_id=%s — %s",
                work_context.user_id,
                request_id,
                type(exc).__name__,
            )
            raise BobNetworkError(
                f"Network error contacting IBM Bob API "
                f"(request_id={request_id}): {exc}"
            ) from exc

        if response.status_code != 200:
            logger.error(
                "IBMBobService: unexpected HTTP %d — user_id=%s request_id=%s",
                response.status_code,
                work_context.user_id,
                request_id,
            )
            raise BobServiceError(
                f"IBM Bob API returned HTTP {response.status_code} "
                f"(request_id={request_id})."
            )

        raw = self._parse_response(response, request_id)

        recommendation_set = RecommendationSet(
            user_id=work_context.user_id,
            recommendations=raw,
            model_version=self._MODEL_VERSION,
            metadata={
                "request_id": request_id,
                "active_sources": work_context.active_sources,
            },
        )

        logger.info(
            "IBMBobService: analysis complete — user_id=%s request_id=%s "
            "recommendations=%d",
            work_context.user_id,
            request_id,
            len(raw),
        )

        return recommendation_set

    def _parse_response(
        self,
        response: httpx.Response,
        request_id: str,
    ) -> list[Recommendation]:
        """
        Parse the IBM Bob JSON response body into a list of Recommendation objects.

        Raises
        ------
        BobResponseError
            If the response body is not valid JSON or the ``recommendations``
            field is absent or contains malformed items.
        """
        try:
            body = response.json()
        except Exception as exc:
            raise BobResponseError(
                f"IBM Bob API returned non-JSON response "
                f"(request_id={request_id})."
            ) from exc

        raw_items = body.get("recommendations")
        if raw_items is None:
            raise BobResponseError(
                f"IBM Bob API response missing 'recommendations' field "
                f"(request_id={request_id})."
            )

        if not isinstance(raw_items, list):
            raise BobResponseError(
                f"IBM Bob API 'recommendations' field must be a list, "
                f"got {type(raw_items).__name__!r} "
                f"(request_id={request_id})."
            )

        recommendations: list[Recommendation] = []
        for i, item in enumerate(raw_items):
            try:
                recommendations.append(Recommendation.model_validate(item))
            except Exception as exc:
                raise BobResponseError(
                    f"IBM Bob API recommendations[{i}] failed validation "
                    f"(request_id={request_id}): {exc}"
                ) from exc

        return recommendations


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class BobError(Exception):
    """
    Base class for all IBM Bob integration errors raised by BobService.

    All Bob-specific exceptions inherit from this class so the Recommendation
    Service (Phase 11) can catch BobError in a single except clause when it
    does not need to distinguish between failure modes.

    Attributes
    ----------
    message : str
        A human-readable description of the failure.  Never contains API
        keys or sensitive request content.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class BobConfigError(BobError):
    """
    Raised when IBMBobService is constructed without required configuration.

    Indicates BOB_API_URL or BOB_API_KEY are missing.  In development,
    use MockBobService instead — it requires no credentials.
    """


class BobServiceError(BobError):
    """
    Raised when the IBM Bob API returns a non-200 response.

    The HTTP status code and a brief description are included in the message.
    The request_id is included for log correlation.
    """


class BobNetworkError(BobError):
    """
    Raised when a network-level failure prevents reaching the IBM Bob API.

    Covers DNS failures, connection refused, and other httpx.RequestError
    subclasses that are not timeouts.
    """


class BobTimeoutError(BobError):
    """
    Raised when the IBM Bob API does not respond within the configured timeout.

    The Recommendation Service should catch this and retain the previous
    cached result rather than surfacing an error to the widget.
    """


class BobResponseError(BobError):
    """
    Raised when the IBM Bob API response is malformed — not valid JSON,
    missing required fields, or failing Pydantic validation.

    Indicates a version mismatch between the Bob API and our models.
    """
