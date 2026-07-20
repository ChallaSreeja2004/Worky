"""
app/recommendations/dependencies.py
=====================================
FastAPI dependency providers for the Recommendation Service layer.

DESIGN RATIONALE
----------------
These functions are the single point of wiring between FastAPI's dependency
injection system and the Recommendation Service.  They ensure:

  • RecommendationService is never instantiated directly inside routers or
    schedulers — it is always obtained through the DI system.
  • BobService is injected into RecommendationService at this layer, keeping
    the two services decoupled from each other.
  • Every caller that requests a RecommendationService receives a fresh
    instance wired to the shared BobService singleton.

WHY NOT A SINGLETON FOR RecommendationService?
-----------------------------------------------
RecommendationService is stateless — it holds no per-user or per-request
state.  It is cheap to construct (a single attribute assignment).  Creating
a new instance per call is therefore safe and avoids any risk of state leaking
between requests.  This matches the pattern used by auth/router.py, which
constructs AuthService per-request via get_auth_service().

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.bob.dependencies
  • app.bob.service          (BobService interface — type annotation only)
  • app.recommendations.service

It must NOT import from:
  • app.connectors.*
  • app.auth
  • app.config
  • app.context_builder
"""

from __future__ import annotations

from app.bob.dependencies import get_bob_service
from app.bob.service import BobService
from app.recommendations.service import RecommendationService


def get_recommendation_service() -> RecommendationService:
    """
    FastAPI dependency provider for RecommendationService.

    Constructs a RecommendationService wired to the shared BobService
    singleton returned by get_bob_service().

    Usage in a router or scheduler:
    ::

        async def my_endpoint(
            rec_service: RecommendationService = Depends(
                get_recommendation_service
            ),
        ) -> ...:
            result = await rec_service.generate(work_context)
    """
    bob_service: BobService = get_bob_service()
    return RecommendationService(bob_service=bob_service)
