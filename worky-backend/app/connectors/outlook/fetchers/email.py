"""
app/connectors/outlook/fetchers/email.py
=========================================
EmailFetcher — retrieves email messages from Microsoft Graph.

RESPONSIBILITIES
----------------
  • Call GraphAPIClient.get_messages() to obtain the raw Graph envelope.
  • Extract and return the ``value`` list (list of raw message dicts).
  • Return an empty list when the inbox has no messages or the key is absent.
  • Let GraphError subclasses propagate — error handling belongs in the
    OutlookConnector one layer up.

WHAT THIS FETCHER DOES NOT DO
------------------------------
  • It does NOT normalise or transform message data.
  • It does NOT filter, sort, or deduplicate messages.
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


class EmailFetcher:
    """
    Fetches email messages for the authenticated user.

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
        fetcher = EmailFetcher(client)
        messages = await fetcher.fetch()
        # messages → list[dict[str, Any]] — raw Graph /me/messages items
    """

    def __init__(self, client: GraphAPIClient) -> None:
        self._client = client

    async def fetch(self) -> list[dict[str, Any]]:
        """
        Fetch email messages from Microsoft Graph.

        Calls ``GET /me/messages`` via the injected GraphAPIClient and
        extracts the ``value`` array from the Graph response envelope.

        Returns
        -------
        list[dict[str, Any]]
            A (possibly empty) list of raw Graph message objects.  Each dict
            contains the fields requested by GraphAPIClient.get_messages():
            ``id``, ``subject``, ``from``, ``receivedDateTime``,
            ``isRead``, ``importance``, ``bodyPreview``, ``hasAttachments``.

            Returns ``[]`` when there are no matching messages or the Graph
            response contains no ``value`` key.

        Raises
        ------
        GraphAuthError
            Propagated from GraphAPIClient when the bearer token is invalid
            or lacks the Mail.Read scope.
        GraphRateLimitError
            Propagated from GraphAPIClient when rate-limiting persists after
            all retries.
        GraphServiceError
            Propagated from GraphAPIClient on any other network, timeout, or
            non-2xx failure.
        """
        logger.debug("EmailFetcher: fetching email messages")

        response = await self._client.get_messages()
        messages: list[dict[str, Any]] = response.get("value", [])

        logger.debug("EmailFetcher: received %d message(s)", len(messages))
        return messages
