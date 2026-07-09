"""
app/connectors/base.py
======================
Shared connector contract for the Worky platform.

DESIGN RATIONALE
----------------
Every enterprise application connector (Outlook, Slack, GitHub, Jira,
Confluence, Calendar …) must implement the BaseConnector abstract class
defined in this module.

This enforces two critical architectural guarantees:

  1. The Context Builder never imports from a specific connector package.
     It depends only on BaseConnector.  Adding a new connector is wiring
     it into the dependency-injection registry — zero changes to the
     Context Builder or any other layer.

  2. IBM Bob always receives a normalised WorkContext regardless of which
     connectors are active for a given user.  It never sees raw Outlook
     objects or raw Slack objects.

SOLID PRINCIPLES APPLIED
-------------------------
  • Single Responsibility  — each connector owns exactly one enterprise
    application.  BaseConnector owns only the shared interface contract.
  • Open / Closed          — the system is open for new connectors
    (add a new sub-class) and closed for modification (existing connectors
    and the Context Builder are untouched).
  • Liskov Substitution    — the Context Builder can hold a list of
    BaseConnector instances and treat them uniformly.  Any concrete
    connector can replace any other without breaking callers.
  • Interface Segregation  — the interface is intentionally minimal.
    Connectors that need extra public methods (e.g., a webhook handler)
    extend their own class; BaseConnector does not bloat.
  • Dependency Inversion   — higher-level modules (Context Builder, Bob
    Service) depend on this abstraction, not on concrete connectors.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

# ConnectorResult is defined in this same package (models.py) and imported
# here so that every connector only needs to import from connectors.base.
from app.connectors.models import ConnectorResult

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """
    Abstract base class that every enterprise connector must implement.

    A connector is responsible for ONE thing: collecting structured data
    from a single enterprise application and returning it as a
    ConnectorResult.  A connector must NOT:

      • Communicate directly with IBM Bob.
      • Communicate directly with the desktop widget.
      • Store application state (connectors are stateless by design).
      • Call another connector (no connector-to-connector dependencies).

    USAGE
    -----
    To implement a new connector, inherit from BaseConnector and provide
    concrete implementations for all abstract methods:

        class SlackConnector(BaseConnector):
            @property
            def source_name(self) -> str:
                return "slack"

            async def get_context(self, user_id: str, access_token: str) -> ConnectorResult:
                ...

            async def health_check(self) -> bool:
                ...

    The connector is then registered in the dependency-injection container
    and the Context Builder picks it up automatically.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        A unique, lowercase, hyphen-separated identifier for this connector.

        Examples: "outlook", "slack", "github", "jira", "confluence"

        This value is used:
          • As the `source` field on every ConnectorResult this connector
            produces, so the Context Builder and Bob can identify where
            each piece of data came from.
          • In structured log lines for traceability.
          • As the key in the WorkContext.sources dictionary.

        Requirements:
          • Must be unique across all registered connectors.
          • Must be stable — renaming it after deployment breaks log queries
            and WorkContext schema compatibility.
        """
        ...

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_context(self, user_id: str, access_token: str) -> ConnectorResult:
        """
        Collect data from the enterprise application and return it as a
        normalised ConnectorResult.

        This is the only method the Context Builder calls.  Implementations
        must be fully async so the Context Builder can run all connectors
        concurrently via asyncio.gather().

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.  Used to look up
            user-specific configuration or preferences if needed.
            The connector must NOT use this to fetch a token — the
            caller (the router or Context Builder) is responsible for
            supplying a valid access_token.

        access_token : str
            A valid, unexpired bearer token scoped to this connector's
            required permissions.  The connector uses this token to make
            API calls on behalf of the user.  The connector must NOT
            refresh tokens internally — token lifecycle is managed by
            the AuthService layer.

        Returns
        -------
        ConnectorResult
            A fully populated ConnectorResult.  On partial failure (e.g.,
            calendar data succeeds but email fetch fails) the connector
            should still return a ConnectorResult with the successfully
            collected data and record the partial error in the `errors`
            field.  It should raise an exception only for total,
            unrecoverable failures.

        Raises
        ------
        ConnectorError
            If the connector cannot retrieve any data at all (e.g., the
            access token is invalid, the downstream API is unreachable,
            or required permissions are missing).
        """
        ...

    # ------------------------------------------------------------------
    # Operational contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verify that the connector can reach its upstream enterprise
        application.

        Used by the /health endpoint and monitoring systems to detect
        when a downstream API is degraded without triggering a full
        context collection cycle.

        Returns
        -------
        bool
            True  — the upstream API is reachable and responding.
            False — the upstream API is unreachable or returning errors.
            This method must NOT raise exceptions; it catches them
            internally and returns False.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience — provided by base class, not overridable
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source='{self.source_name}'>"


# ---------------------------------------------------------------------------
# Connector-specific exception hierarchy
# ---------------------------------------------------------------------------

class ConnectorError(Exception):
    """
    Base exception for all connector errors.

    Raised when a connector encounters an unrecoverable failure — i.e.,
    it cannot return any meaningful data for the current request.

    All connector-specific exceptions should inherit from this class so
    that the Context Builder can catch ConnectorError in a single except
    clause without needing to know which connector raised it.

    Attributes
    ----------
    source : str
        The source_name of the connector that raised the error.
        Populated automatically when using ConnectorError.for_source().
    message : str
        A human-readable description of the failure.
    """

    def __init__(self, source: str, message: str) -> None:
        self.source = source
        self.message = message
        super().__init__(f"[{source}] {message}")

    @classmethod
    def for_source(cls, source: str, message: str) -> "ConnectorError":
        """Factory method for readable construction at the call site."""
        return cls(source=source, message=message)


class ConnectorAuthError(ConnectorError):
    """
    Raised when the connector's access token is invalid, expired, or
    lacks the required permissions.

    The AuthService should catch this and trigger a token refresh or
    re-authentication flow.
    """


class ConnectorTimeoutError(ConnectorError):
    """
    Raised when the upstream enterprise application does not respond
    within the connector's configured timeout.
    """


class ConnectorRateLimitError(ConnectorError):
    """
    Raised when the upstream API returns a 429 Too Many Requests response
    and all retry attempts have been exhausted.
    """
