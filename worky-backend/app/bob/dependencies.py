"""
app/bob/dependencies.py
========================
FastAPI dependency providers for the IBM Bob service layer.

DESIGN RATIONALE
----------------
These functions are the single point of wiring between FastAPI's dependency
injection system and the Bob layer.  They ensure:

  • BobService is never instantiated directly inside routers or schedulers.
  • The concrete implementation (MockBobService in development,
    IBMBobService in production) is swapped at this single location when
    the deployment environment changes.
  • Every caller that needs a BobService gets the same shared singleton
    instance, keeping the service stateless and consistent.

SWITCHING FROM MOCK TO IBM BOB
------------------------------
To switch to IBMBobService when real credentials become available, change
_get_shared_bob_service() to:

    from app.bob.service import IBMBobService
    from app.bob.settings import get_bob_settings

    @lru_cache
    def _get_shared_bob_service() -> IBMBobService:
        settings = get_bob_settings()
        return IBMBobService(
            api_url=settings.bob_api_url,
            api_key=settings.bob_api_key,
            timeout=settings.bob_timeout_seconds,
        )

Zero changes are required in any caller — they depend only on BobService.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.bob.service
  • app.bob.mock_service
  • app.bob.settings      (when switching to IBMBobService)

It must NOT import from connectors, context_builder (except via BobService
interface), auth, or recommendations packages.
"""

from __future__ import annotations

from functools import lru_cache

from app.bob.mock_service import MockBobService
from app.bob.service import BobService


@lru_cache
def _get_shared_bob_service() -> MockBobService:
    """
    Return the process-wide singleton BobService implementation.

    lru_cache ensures the service is constructed only once per process
    lifetime.  MockBobService is used by default — it requires no
    credentials and works without internet access.

    To switch to IBMBobService for production, replace this function's
    body and return type as documented in the module docstring above.
    Zero changes are required elsewhere.
    """
    return MockBobService()


def get_bob_service() -> BobService:
    """
    FastAPI dependency provider for BobService.

    Returns the shared singleton BobService implementation.
    Callers declare BobService as their dependency type so they remain
    decoupled from the concrete implementation.

    Usage in a router or scheduler:
    ::

        async def my_endpoint(
            bob_service: BobService = Depends(get_bob_service),
        ) -> ...:
            recommendation_set = await bob_service.analyze(work_context)
    """
    return _get_shared_bob_service()
