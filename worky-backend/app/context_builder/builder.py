"""
app/context_builder/builder.py
================================
ContextBuilder — concurrent connector aggregation layer.

RESPONSIBILITIES
----------------
  • Accept a list of already-initialised BaseConnector instances.
  • Run all connectors concurrently via asyncio.gather().
  • Isolate individual connector failures so they cannot abort other connectors.
  • Assemble all ConnectorResult objects into a single WorkContext.
  • Attach assembly metadata (duration, connector count) for observability.

WHAT THIS MODULE DOES NOT DO
------------------------------
  • It does NOT construct connectors.  Callers supply ready-made instances.
  • It does NOT manage token lifecycle.  access_token is forwarded to each
    connector solely to satisfy the BaseConnector.get_context() contract.
    Authentication is the responsibility of the caller and individual connectors.
  • It does NOT inspect ConnectorResult.data.  The data dict is passed wholesale
    to WorkContext — ContextBuilder has no knowledge of its contents.
  • It does NOT call IBM Bob.  That is the Recommendation Service's concern.
  • It does NOT cache results.  Each call performs a fresh collection cycle.
  • It does NOT contain any FastAPI routing or HTTP logic.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.base   (BaseConnector)
  • app.connectors.models (ConnectorResult)
  • app.context_builder.models (WorkContext)

It must NOT import from:
  • app.connectors.outlook.*
  • app.connectors.slack.*
  • Any other connector sub-package
  • app.auth
  • app.config
  • app.bob
  • app.recommendations
  • fastapi
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
from app.context_builder.models import WorkContext

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Stateless orchestrator that runs a list of connectors concurrently and
    assembles their results into a single WorkContext.

    ContextBuilder is intentionally stateless — it holds no connectors and
    owns no connector lifetime.  The caller supplies a fully-initialised
    connector list on every build() call.  This keeps token lifecycle,
    connector construction, and aggregation logic in separate, independent
    layers.

    Usage
    -----
    ::

        builder = ContextBuilder()

        connectors = [
            OutlookConnector(graph_client=GraphAPIClient(token), normalizer=...),
            SlackConnector(client=SlackAPIClient(token), ...),
        ]

        work_context = await builder.build(
            user_id=user_id,
            connectors=connectors,
            access_token=access_token,
        )
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def build(
        self,
        user_id: str,
        connectors: list[BaseConnector],
        access_token: str,
    ) -> WorkContext:
        """
        Run all connectors concurrently and assemble the results into a
        WorkContext.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.  Forwarded to each
            connector's get_context() call and embedded in the WorkContext.

        connectors : list[BaseConnector]
            Fully-initialised connector instances to run.  May be empty —
            an empty list returns an empty WorkContext without error.

        access_token : str
            A valid bearer token forwarded to each connector's get_context()
            call.  ContextBuilder does not inspect, store, or refresh this
            token.  Token lifecycle is the caller's responsibility; the token
            is passed here solely to satisfy the BaseConnector contract.

        Returns
        -------
        WorkContext
            A fully assembled WorkContext containing all usable connector
            data, per-connector status summaries, any errors encountered,
            and assembly metadata.
        """
        logger.info(
            "ContextBuilder: build starting — user_id=%s connectors=%d",
            user_id,
            len(connectors),
        )

        start = time.monotonic()

        results: tuple[ConnectorResult, ...] = await asyncio.gather(
            *[
                self._collect_connector(connector, user_id, access_token)
                for connector in connectors
            ]
        )

        elapsed_ms = round((time.monotonic() - start) * 1000)

        work_context = WorkContext.from_connector_results(
            user_id=user_id,
            results=list(results),
            metadata={
                "assembly_duration_ms": elapsed_ms,
                "connector_count": len(connectors),
            },
        )

        logger.info(
            "ContextBuilder: build complete — user_id=%s active_sources=%s "
            "duration_ms=%d",
            user_id,
            work_context.active_sources,
            elapsed_ms,
        )

        return work_context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_connector(
        self,
        connector: BaseConnector,
        user_id: str,
        access_token: str,
    ) -> ConnectorResult:
        """
        Call one connector and return its ConnectorResult.

        This method is the safety boundary for the aggregation layer.  The
        normal expectation is that every BaseConnector implementation handles
        its own exceptions internally and returns ConnectorResult.failed()
        on total failure — they must never raise from get_context().

        In the event that a connector violates that contract (programming
        error, unhandled library exception, etc.), this wrapper catches the
        exception and converts it into a FAILED ConnectorResult so the rest
        of the build cycle is unaffected.

        Parameters
        ----------
        connector : BaseConnector
            The connector to call.
        user_id : str
            Forwarded to connector.get_context().
        access_token : str
            Forwarded to connector.get_context().  See build() docstring
            for the token-forwarding rationale.

        Returns
        -------
        ConnectorResult
            Either the connector's own result, or a synthesised FAILED
            result if the connector raised an unexpected exception.
        """
        try:
            return await connector.get_context(
                user_id=user_id,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "ContextBuilder: unexpected exception from connector '%s' — %s: %s",
                connector.source_name,
                type(exc).__name__,
                exc,
            )
            return ConnectorResult.failed(
                source=connector.source_name,
                errors=[
                    f"Unexpected connector error ({type(exc).__name__}): {exc}"
                ],
            )
