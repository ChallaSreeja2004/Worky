"""
app/context_builder/models.py
==============================
WorkContext — the unified work context sent to IBM Bob for reasoning.

DESIGN RATIONALE
----------------
WorkContext is the single payload that the Context Builder assembles from
all active connector results and hands to the BobService.  It represents
a complete, point-in-time snapshot of a user's work environment across
every integrated enterprise application.

IBM Bob's only input is a WorkContext.  Bob never interacts with individual
connectors, never calls Microsoft Graph, never calls the Slack API.  The
entire complexity of multi-connector aggregation is invisible to Bob — it
receives one clean, structured payload and returns a RecommendationSet.

This design ensures:
  • IBM Bob can be swapped, versioned, or mocked without touching any
    connector.
  • The WorkContext schema is the versioned API surface with Bob.  Schema
    changes here require a deliberate, coordinated update.
  • Connectors are entirely decoupled from Bob's reasoning logic.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • Pydantic
  • app.connectors.models (ConnectorResult, ConnectorStatus)

It must NOT import from any connector sub-package or from app.bob.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.connectors.models import ConnectorResult, ConnectorStatus


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------

class ConnectorSummary(BaseModel):
    """
    Lightweight summary of a single connector's contribution to the
    WorkContext.  Included in WorkContext.connector_summaries so IBM Bob
    can understand which data sources were active, healthy, or degraded
    without iterating through every source entry.

    Fields
    ------
    source : str
        Connector identifier (e.g., "outlook", "slack").

    status : ConnectorStatus
        Final status of the connector's data collection attempt.

    collected_at : datetime
        When this connector's data was gathered.

    error_count : int
        Number of errors recorded.  Zero on full success.
    """

    source: str
    status: ConnectorStatus
    collected_at: datetime
    error_count: int = 0


# ---------------------------------------------------------------------------
# WorkContext
# ---------------------------------------------------------------------------

class WorkContext(BaseModel):
    """
    The unified work context representing a user's complete enterprise
    environment at a specific point in time.

    This is the ONLY object passed to IBM Bob (via BobService.analyze).
    The Context Builder constructs it by:
      1. Running all registered connectors concurrently.
      2. Collecting their ConnectorResult outputs.
      3. Populating this model with the aggregated data.

    Fields
    ------
    user_id : str
        The Worky-internal user identifier.  IBM Bob uses this to
        personalise recommendations (user history, preferences, etc.).

    assembled_at : datetime
        UTC timestamp of when the Context Builder finished assembling
        this WorkContext.  IBM Bob uses this to reason about the overall
        freshness of the context snapshot.

    sources : dict[str, dict[str, Any]]
        The core payload.  Keyed by connector source_name; each value is
        the raw `data` dictionary from that connector's ConnectorResult.

        Example shape:
          {
            "outlook": {
              "calendar_events": [...],
              "emails": [...],
              "user": {...}
            },
            "slack": {
              "unread_messages": [...],
              "mentions": [...]
            }
          }

        IBM Bob iterates over this dictionary to understand what is
        happening across all of the user's enterprise applications.

    connector_summaries : list[ConnectorSummary]
        One summary entry per connector that participated in this context
        assembly cycle, including connectors that failed.  Bob uses this
        to understand data gaps (e.g., "GitHub data is missing because the
        connector failed — do not make recommendations about open PRs").

    errors : dict[str, list[str]]
        Keyed by connector source_name.  Contains error messages from
        connectors that recorded PARTIAL or FAILED status.  Present so
        Bob and downstream observability tools can surface data-quality
        warnings to the user.

        Example:
          {"outlook": ["Email fetch timed out after 10s"]}

    metadata : dict[str, Any]
        Context-level operational metadata.  Examples:
          • {"total_connectors": 3, "successful_connectors": 2}
          • {"assembly_duration_ms": 843}
        Not consumed by IBM Bob.  Used by monitors and dashboards.
    """

    user_id: str = Field(
        ...,
        description="Worky-internal user identifier.",
    )

    assembled_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the Context Builder finished assembly.",
    )

    sources: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Aggregated connector payloads keyed by connector source_name. "
            "Each value is the connector's normalised data dictionary."
        ),
    )

    connector_summaries: list[ConnectorSummary] = Field(
        default_factory=list,
        description="Per-connector status summaries including failed connectors.",
    )

    errors: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Connector-level errors keyed by source_name.  Empty on full success.",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata for observability.  Not consumed by IBM Bob.",
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[misc]
    @property
    def active_sources(self) -> list[str]:
        """
        List of connector source names that contributed usable data.
        Excludes connectors with FAILED status.
        """
        return [
            s.source
            for s in self.connector_summaries
            if s.status != ConnectorStatus.FAILED
        ]

    @computed_field  # type: ignore[misc]
    @property
    def has_errors(self) -> bool:
        """True if any connector reported errors."""
        return bool(self.errors)

    @computed_field  # type: ignore[misc]
    @property
    def total_connectors(self) -> int:
        """Total number of connectors that participated in this cycle."""
        return len(self.connector_summaries)

    @computed_field  # type: ignore[misc]
    @property
    def successful_connectors(self) -> int:
        """Number of connectors that returned SUCCESS status."""
        return sum(
            1 for s in self.connector_summaries
            if s.status == ConnectorStatus.SUCCESS
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_connector_results(
        cls,
        user_id: str,
        results: list[ConnectorResult],
        metadata: dict[str, Any] | None = None,
    ) -> "WorkContext":
        """
        Construct a WorkContext from a list of ConnectorResult objects.

        This is the standard way the Context Builder creates a WorkContext.
        It handles:
          • Separating usable data from failed connectors.
          • Building the connector_summaries list.
          • Aggregating errors by source.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.

        results : list[ConnectorResult]
            All ConnectorResult objects returned by the connectors,
            including FAILED ones.  The factory gracefully handles mixed
            statuses.

        metadata : dict[str, Any], optional
            Context-level metadata (e.g., assembly duration) to attach.

        Returns
        -------
        WorkContext
            A fully assembled WorkContext ready to be sent to BobService.

        Usage
        -----
            connector_results = await asyncio.gather(
                *[c.get_context(user_id, token) for c in connectors],
                return_exceptions=False,   # ConnectorError is handled inside each connector
            )
            work_context = WorkContext.from_connector_results(
                user_id=user_id,
                results=connector_results,
                metadata={"assembly_duration_ms": elapsed_ms},
            )
        """
        sources: dict[str, dict[str, Any]] = {}
        summaries: list[ConnectorSummary] = []
        errors: dict[str, list[str]] = {}

        for result in results:
            # Always record the summary — even for failed connectors.
            summaries.append(
                ConnectorSummary(
                    source=result.source,
                    status=result.status,
                    collected_at=result.collected_at,
                    error_count=len(result.errors),
                )
            )

            # Only include data from connectors that returned something usable.
            if result.is_usable and result.data:
                sources[result.source] = result.data

            # Record errors regardless of whether data was usable.
            if result.has_errors:
                errors[result.source] = result.errors

        return cls(
            user_id=user_id,
            sources=sources,
            connector_summaries=summaries,
            errors=errors,
            metadata=metadata or {},
        )

    model_config = {"frozen": False}
