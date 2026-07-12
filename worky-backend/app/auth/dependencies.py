"""
app/auth/dependencies.py
========================
FastAPI dependency providers for the authentication layer.

DESIGN RATIONALE
----------------
These functions are the single point of wiring between FastAPI's dependency
injection system and the auth layer.  They ensure:

  • AuthService is never instantiated directly inside routers.
  • The TokenRepository implementation (InMemoryTokenRepository for now) is
    swapped at this single location when a persistent backend is introduced.
  • Every request that needs an AuthService gets the same shared repository
    instance (via module-level singleton), keeping tokens consistent across
    requests within a single process.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.auth.repository
  • app.auth.service

It must NOT import from connectors, context_builder, or bob packages.
"""

from __future__ import annotations

from functools import lru_cache

from app.auth.repository import InMemoryTokenRepository, TokenRepository
from app.auth.service import AuthService


@lru_cache
def _get_shared_token_repository() -> InMemoryTokenRepository:
    """
    Return the process-wide singleton InMemoryTokenRepository.

    lru_cache ensures all requests within the same process share the same
    repository instance — tokens saved during /callback are visible when
    /refresh is called later.

    To swap in a persistent backend (e.g., Redis), replace this function's
    return value.  Zero changes to AuthService or the routers are required.
    """
    return InMemoryTokenRepository()


def get_token_repository() -> TokenRepository:
    """
    FastAPI dependency provider for TokenRepository.

    Usage in a router:
        @router.get("/example")
        async def example(repo: TokenRepository = Depends(get_token_repository)):
            ...
    """
    return _get_shared_token_repository()


def get_auth_service() -> AuthService:
    """
    FastAPI dependency provider for AuthService.

    Constructs an AuthService wired to the shared token repository.
    Called on every request that declares AuthService as a dependency.

    Usage in a router:
        @router.get("/example")
        async def example(auth: AuthService = Depends(get_auth_service)):
            ...
    """
    return AuthService(token_repository=_get_shared_token_repository())
