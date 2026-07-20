"""
app/connectors/outlook/connector.py
=====================================
OutlookConnector — BaseConnector implementation for Microsoft Outlook.

RESPONSIBILITIES
----------------
  • Implement the BaseConnector interface for the Outlook enterprise application.
  • Accept a pre-built GraphAPIClient and OutlookNormalizer via constructor injection.
  • Run CalendarFetcher and EmailFetcher concurrently via asyncio.gather().
  • Normalize both raw payloads into an OutlookContext via OutlookNormalizer.
  • Return ConnectorResult.success() when both fetchers succeed.
  • Return ConnectorResult.partial() when exactly one fetcher fails.
  • Return ConnectorResult.failed() when both fetchers fail.
  • Implement health_check() via GraphAPIClient.ping() — never raises.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT call the Microsoft token endpoint.
  • It does NOT refresh tokens — callers must provide a valid access_token.
  • It does NOT call IBM Bob.
  • It does NOT know about ContextBuilder or WorkContext.
  • It does NOT import from app.auth — AuthService wires the token before calling.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.base
  • app.connectors.models
  • app.connectors.outlook.graph_client
  • app.connectors.outlook.fetchers.calendar
  • app.connectors.outlook.fetchers.email
  • app.connectors.outlook.normalizer
  • app.connectors.outlook.models

It must NOT import from:
  • app.auth
  • app.config
  • app.context_builder
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
from app.connectors.outlook.fetchers.calendar import CalendarFetcher
from app.connectors.outlook.fetchers.email import EmailFetcher
from app.connectors.outlook.graph_client import GraphAPIClient
from app.connectors.outlook.normalizer import OutlookNormalizer

logger = logging.getLogger(__name__)


class OutlookConnector(BaseConnector):
    """
    Collects calendar events and email messages from Microsoft Outlook
    via the Microsoft Graph API and returns a normalised ConnectorResult.

    Parameters
    ----------
    graph_client : GraphAPIClient
        An authenticated Graph API client carrying a valid access_token for
        the current user.  Must be constructed by the caller before passing
        to this connector.

    normalizer : OutlookNormalizer
        The normalizer used to convert raw Graph dicts into OutlookContext.
        Injected so it can be replaced with a test double.

    Example
    -------
    ::

        client = GraphAPIClient(access_token=token)
        normalizer = OutlookNormalizer()
        connector = OutlookConnector(graph_client=client, normalizer=normalizer)
        result = await connector.get_context(user_id="u1", access_token=token)
    """

    def __init__(
        self,
        graph_client: GraphAPIClient,
        normalizer: OutlookNormalizer,
    ) -> None:
        self._client = graph_client
        self._normalizer = normalizer

    # ------------------------------------------------------------------
    # BaseConnector — identity
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        """Unique identifier for this connector.  Matches WorkContext key."""
        return "outlook"

    # ------------------------------------------------------------------
    # BaseConnector — core contract
    # ------------------------------------------------------------------

    async def get_context(self, user_id: str, access_token: str) -> ConnectorResult:
        """
        Fetch today's calendar events and email messages concurrently, then
        normalise and return the result as a ConnectorResult.

        Both fetchers run concurrently via asyncio.gather(return_exceptions=True).
        This ensures a single failing fetcher does not block the other.

        Returns
        -------
        ConnectorResult
            ConnectorResult.success()  — both fetchers succeeded.
            ConnectorResult.partial()  — one fetcher failed; partial data included.
            ConnectorResult.failed()   — both fetchers failed; no data available.
        """
        calendar_fetcher = CalendarFetcher(self._client)
        email_fetcher = EmailFetcher(self._client)

        logger.debug(
            "OutlookConnector: starting concurrent fetch for user_id=%s", user_id
        )

        calendar_result, email_result = await asyncio.gather(
            calendar_fetcher.fetch(),
            email_fetcher.fetch(),
            return_exceptions=True,
        )

        # Determine which fetches succeeded and which failed.
        raw_events: list[dict[str, Any]] = []
        raw_messages: list[dict[str, Any]] = []
        errors: list[str] = []

        if isinstance(calendar_result, BaseException):
            errors.append(f"Calendar fetch failed: {calendar_result}")
            logger.warning(
                "OutlookConnector: calendar fetch failed for user_id=%s — %s",
                user_id,
                calendar_result,
            )
        else:
            raw_events = calendar_result

        if isinstance(email_result, BaseException):
            errors.append(f"Email fetch failed: {email_result}")
            logger.warning(
                "OutlookConnector: email fetch failed for user_id=%s — %s",
                user_id,
                email_result,
            )
        else:
            raw_messages = email_result

        # Both fetchers failed — return FAILED with no data.
        if len(errors) == 2:
            logger.error(
                "OutlookConnector: both fetchers failed for user_id=%s", user_id
            )
            return ConnectorResult.failed(
                source=self.source_name,
                errors=errors,
            )

        # Normalize whatever data was successfully collected.
        outlook_context = self._normalizer.normalize(
            raw_events=raw_events,
            raw_messages=raw_messages,
        )

        data: dict[str, Any] = outlook_context.model_dump()

        # One fetcher failed — return PARTIAL with the data that was collected.
        if errors:
            logger.warning(
                "OutlookConnector: partial result for user_id=%s", user_id
            )
            return ConnectorResult.partial(
                source=self.source_name,
                data=data,
                errors=errors,
            )

        # Both fetchers succeeded — return SUCCESS.
        logger.debug(
            "OutlookConnector: full success for user_id=%s", user_id
        )
        return ConnectorResult.success(
            source=self.source_name,
            data=data,
        )

    # ------------------------------------------------------------------
    # BaseConnector — operational contract
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        Verify that the Microsoft Graph API is reachable.

        Delegates to GraphAPIClient.ping() which returns True/False and
        never raises.  This method therefore also never raises.

        Returns
        -------
        bool
            True  — Graph API is reachable and the token is valid.
            False — Graph API is unreachable or the token is invalid.
        """
        return await self._client.ping()
