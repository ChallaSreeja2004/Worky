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
    BobCLIService in production) is swapped at this single location.
  • Every caller that needs a BobService gets the same shared singleton
    instance, keeping the service stateless and consistent.

CURRENT IMPLEMENTATION
----------------------
BobCLIService is active.  It invokes Bob Shell as a subprocess, sends the
WorkContext via stdin, and parses the stream-json output.

Bob Shell must be installed and authenticated before starting the server.
Verify with:  bob --version

SWITCHING BACK TO MOCK (e.g. for CI without Bob Shell)
-------------------------------------------------------
Replace _get_shared_bob_service() with:

    from app.bob.mock_service import MockBobService

    @lru_cache
    def _get_shared_bob_service() -> MockBobService:
        return MockBobService()

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.bob.service
  • app.bob.mock_service
  • app.bob.cli_service
  • app.bob.settings

It must NOT import from connectors, context_builder (except via BobService
interface), auth, or recommendations packages.
"""

from __future__ import annotations

from functools import lru_cache

from app.bob.cli_service import BobCLIService
from app.bob.service import BobService
from app.bob.settings import get_bob_settings


@lru_cache
def _get_shared_bob_service() -> BobCLIService:
    """
    Return the process-wide singleton BobService implementation.

    lru_cache ensures the service is constructed only once per process
    lifetime.  BobCLIService invokes Bob Shell as a subprocess — Bob Shell
    must be installed and authenticated on the host machine.

    Configuration is read from BobSettings (BOB_EXECUTABLE, BOB_CHAT_MODE,
    BOB_TIMEOUT_SECONDS in .env).  All settings have sensible defaults so
    no .env changes are required if bob is on PATH.
    """
    settings = get_bob_settings()
    return BobCLIService(
        bob_executable=settings.bob_executable,
        chat_mode=settings.bob_chat_mode,
        timeout=settings.bob_timeout_seconds,
    )


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
