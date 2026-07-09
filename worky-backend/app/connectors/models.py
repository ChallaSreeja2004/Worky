"""
app/connectors/models.py
========================
Shared Pydantic models that form the contract between every connector and
the Context Builder.

DESIGN RATIONALE
----------------
ConnectorResult is the single standard output type of every connector in
the Worky platform.  It is intentionally generic:

  • The `data` field is typed as dict[str, Any].  Each connector
    populates it with its own normalised payload (OutlookContext,
    SlackContext, etc.).  The Context Builder receives all results as
    ConnectorResult objects and never inspects connector-specific fields
    directly — it passes them wholesale to the WorkContext.

  • Using a concrete union type (OutlookContext | SlackContext | …) would
    force the Context Builder to import every connector's internal models,
    creating the tight coupling we are explicitly preventing.

  • Downstream consumers that need connector-specific fields (e.g., a
    future Outlook-specific recommendation rule) parse the `data` dict
    against the connector's own Pydantic model using model_validate().
    This is explicit and safe without coupling the shared contract to any
    single connector.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • Pydantic
  • app.connectors.enums  (if created in future)

It must NOT import from any connector sub-package (outlook/, slack/ …)
or from app.context_builder.  Violations create circular imports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ConnectorStatus(str, Enum):
    """
    Terminal status of a connector's data collection attempt.

    SUCCESS
        All requested data was collected without errors.

    PARTIAL
        Some data was collected but one or more sub-fetches failed
        (e.g., calendar events succeeded but email fetch timed out).
        The Context Builder should still include partial results in
        the WorkContext rather than discarding them entirely.

    FAILED
        The connector could not collect any data.  The `errors` list
        will contain at least one entry explaining the failure.
        The Context Builder records this as a source-level error in the
        WorkContext and continues with other connectors.
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED  = "failed"


# ---------------------------------------------------------------------------
# ConnectorResult
# ---------------------------------------------------------------------------

class ConnectorResult(BaseModel):
    """
    The standard output contract of every BaseConnector implementation.

    Every connector's get_context() method must return a ConnectorResult.
    The Context Builder aggregates a list of ConnectorResults into a
    single WorkContext that is sent to IBM Bob.

    Fields
    ------
    source : str
        The connector's unique identifier (e.g., "outlook", "slack").
        Must match BaseConnector.source_name exactly.

    status : ConnectorStatus
        Whether the data collection succeeded, partially succeeded, or
        failed entirely.  The Context Builder uses this to decide whether
        to include the result in the WorkContext and whether to surface
        a warning to the user.

    collected_at : datetime
        UTC timestamp of when the connector finished data collection.
        Used by IBM Bob to reason about data freshness — a stale result
        from five minutes ago should be weighted differently from a
        result collected ten seconds ago.

    data : dict[str, Any]
        The connector's normalised payload.  Each connector documents the
        exact shape of this dictionary in its own models.py file.

        Examples:
          Outlook  → {"calendar_events": [...], "emails": [...], "user": {...}}
          Slack    → {"unread_messages": [...], "mentions": [...]}
          GitHub   → {"open_prs": [...], "review_requests": [...]}

        Consumers that need to work with typed fields should validate
        this dict against the connector's own Pydantic model:

            from app.connectors.outlook.models import OutlookContext
            outlook_ctx = OutlookContext.model_validate(result.data)

    errors : list[str]
        Human-readable descriptions of any errors encountered during
        data collection.  Empty on full success.  On PARTIAL status,
        contains one entry per failed sub-fetch.  On FAILED status,
        contains the root cause.

        Errors are informational — they are logged and included in the
        WorkContext metadata so Bob can reason about data gaps.

    metadata : dict[str, Any]
        Optional key-value pairs the connector may attach for
        observability or debugging purposes.  Examples:
          • {"api_calls_made": 3, "latency_ms": 412}
          • {"graph_api_version": "v1.0"}
          • {"rate_limit_remaining": 98}
        The Context Builder passes this through to WorkContext unchanged.
        IBM Bob does not consume metadata — it is for humans and monitors.
    """

    source: str = Field(
        ...,
        description="Unique connector identifier matching BaseConnector.source_name.",
        examples=["outlook", "slack", "github"],
    )

    status: ConnectorStatus = Field(
        ...,
        description="Terminal status of the data collection attempt.",
    )

    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when data collection completed.",
    )

    data: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Connector-specific normalised payload.  Shape is documented "
            "in each connector's own models.py."
        ),
    )

    errors: list[str] = Field(
        default_factory=list,
        description="Descriptions of any errors encountered.  Empty on full success.",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata for observability.  Not consumed by IBM Bob.",
    )

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def success(
        cls,
        source: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> "ConnectorResult":
        """
        Construct a fully-successful ConnectorResult.

        Usage inside a connector:

            return ConnectorResult.success(
                source=self.source_name,
                data=normalizer.to_dict(outlook_context),
                metadata={"api_calls_made": 3},
            )
        """
        return cls(
            source=source,
            status=ConnectorStatus.SUCCESS,
            data=data,
            metadata=metadata or {},
        )

    @classmethod
    def partial(
        cls,
        source: str,
        data: dict[str, Any],
        errors: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> "ConnectorResult":
        """
        Construct a partial ConnectorResult where some data was collected
        but at least one sub-fetch failed.

        Usage inside a connector:

            return ConnectorResult.partial(
                source=self.source_name,
                data={"calendar_events": events},   # emails failed
                errors=["Email fetch timed out after 10s"],
                metadata={"api_calls_made": 1},
            )
        """
        return cls(
            source=source,
            status=ConnectorStatus.PARTIAL,
            data=data,
            errors=errors,
            metadata=metadata or {},
        )

    @classmethod
    def failed(
        cls,
        source: str,
        errors: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> "ConnectorResult":
        """
        Construct a fully-failed ConnectorResult.

        Usage inside a connector's exception handler:

            except ConnectorAuthError as exc:
                return ConnectorResult.failed(
                    source=self.source_name,
                    errors=[str(exc)],
                )
        """
        return cls(
            source=source,
            status=ConnectorStatus.FAILED,
            data={},
            errors=errors,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_usable(self) -> bool:
        """
        True if the result contains data the Context Builder can include
        in the WorkContext (SUCCESS or PARTIAL).  False if FAILED.
        """
        return self.status != ConnectorStatus.FAILED

    @property
    def has_errors(self) -> bool:
        """True if any errors were recorded, regardless of status."""
        return len(self.errors) > 0

    model_config = {"frozen": False}
