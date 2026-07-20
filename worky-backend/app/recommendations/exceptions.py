"""
app/recommendations/exceptions.py
===================================
RecommendationService-specific exception types.

DESIGN RATIONALE
----------------
The Recommendation Service wraps BobService calls.  Most failure modes
(network errors, timeouts, API errors, malformed responses) are already
expressed by the Bob exception hierarchy (BobError and its subclasses).
The Recommendation Service re-raises those directly when no additional
context is needed.

Only one additional exception type is warranted at this layer:

  RecommendationError
      A thin wrapper raised when the Recommendation Service encounters a
      failure that is specific to its own orchestration logic — for example,
      an empty or None WorkContext being passed by the caller.

      Callers that want to catch any failure from this layer in a single
      clause may catch ``RecommendationError | BobError``, or catch each
      individually to distinguish between orchestration failures and
      downstream AI failures.

IMPORT RULES
------------
This module may only import from:
  • Python standard library

It must NOT import from:
  • app.bob
  • app.connectors.*
  • app.auth
  • app.config
  • app.context_builder
"""

from __future__ import annotations


class RecommendationError(Exception):
    """
    Raised when the RecommendationService encounters an orchestration-level
    failure that originates within this layer rather than in BobService.

    Examples
    --------
    - The caller passed a None WorkContext.
    - The WorkContext user_id is empty.

    For BobService-level failures (network, timeout, bad response), the
    Bob exception hierarchy (BobError subclasses) is propagated directly
    without wrapping so callers can distinguish failure origins precisely.

    Attributes
    ----------
    message : str
        Human-readable description of the failure.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
