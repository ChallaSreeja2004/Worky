"""
app/connectors/outlook/fetchers/calendar.py
============================================
CalendarFetcher — retrieves today's calendar events from Microsoft Graph.

RESPONSIBILITIES
----------------
  • Call GraphAPIClient.get_calendar_events() to obtain the raw Graph envelope.
  • Extract and return the ``value`` list (list of raw event dicts).
  • Return an empty list when the calendar has no events or the key is absent.
  • Let GraphError subclasses propagate — error handling belongs in the
    OutlookConnector one layer up.

WHAT THIS FETCHER DOES NOT DO
------------------------------
  • It does NOT normalise or transform event data.
  • It does NOT filter, sort, or deduplicate events.
  • It does NOT catch any exceptions.
  • It does NOT know about ConnectorResult, WorkContext, or IBM Bob.
  • It does NOT refresh tokens or manage authentication.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.outlook.graph_client  (GraphAPIClient only)

It must NOT import from:
  • app.auth
  • app.config
  • app.connectors.base
  • app.connectors.models
  • app.context_builder
"""

from __future__ import annotations

import logging
from typing import Any

from app.connectors.outlook.graph_client import GraphAPIClient

logger = logging.getLogger(__name__)


class CalendarFetcher:
    """
    Fetches today's calendar events for the authenticated user.

    Thin adapter between GraphAPIClient and the normalizer.  Construct it
    with a ready-to-use ``GraphAPIClient`` and call ``fetch()`` once per
    connector execution cycle.

    Parameters
    ----------
    client : GraphAPIClient
        An authenticated Graph API client scoped to the current user.
        Must already carry a valid, unexpired bearer token.

    Example
    -------
    ::

        client = GraphAPIClient(access_token=token)
        fetcher = CalendarFetcher(client)
        events = await fetcher.fetch()
        # events → list[dict[str, Any]] — raw Graph /me/calendarView items
    """

    def __init__(self, client: GraphAPIClient) -> None:
        self._client = client

    async def fetch(self) -> list[dict[str, Any]]:
        """
        Fetch today's calendar events from Microsoft Graph.

        Calls ``GET /me/calendarView`` via the injected GraphAPIClient and
        extracts the ``value`` array from the Graph response envelope.

        Returns
        -------
        list[dict[str, Any]]
            A (possibly empty) list of raw Graph event objects.  Each dict
            contains the fields requested by GraphAPIClient.get_calendar_events():
            ``id``, ``subject``, ``start``, ``end``, ``location``,
            ``organizer``, ``isAllDay``, ``isCancelled``, ``onlineMeeting``,
            ``bodyPreview``.

            Returns ``[]`` when today's calendar is empty or the Graph response
            contains no ``value`` key.

        Raises
        ------
        GraphAuthError
            Propagated from GraphAPIClient when the bearer token is invalid
            or lacks the Calendars.Read scope.
        GraphRateLimitError
            Propagated from GraphAPIClient when rate-limiting persists after
            all retries.
        GraphServiceError
            Propagated from GraphAPIClient on any other network, timeout, or
            non-2xx failure.
        """
        logger.debug("CalendarFetcher: fetching today's calendar events")

        response = await self._client.get_calendar_events()
        events: list[dict[str, Any]] = response.get("value", [])

        logger.debug("CalendarFetcher: received %d event(s)", len(events))
        return events
