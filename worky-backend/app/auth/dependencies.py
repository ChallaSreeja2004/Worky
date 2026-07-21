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
  • Every request that needs an AuthService gets the SAME AuthService instance
    (via _get_shared_auth_service), so the in-process PKCE verifier map
    (_pkce_store) populated during /auth/login is still present when
    /auth/callback arrives on a subsequent request.

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


@lru_cache
def _get_shared_auth_service() -> AuthService:
    """
    Return the process-wide singleton AuthService.

    AuthService holds an in-process PKCE verifier map (_pkce_store) that is
    populated by get_authorization_url() during /auth/login and consumed by
    exchange_code_for_tokens() during /auth/callback.  Because these two
    endpoints are handled by different HTTP requests, they must share the
    same AuthService instance — otherwise _pkce_store is empty on the
    callback request and state validation fails with "Unknown or expired
    state parameter."

    lru_cache (with no arguments) returns the same instance on every call
    within the same process, matching the lifetime of the PKCE verifier.
    """
    return AuthService(token_repository=_get_shared_token_repository())


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

    Returns the process-wide singleton AuthService so that the PKCE verifier
    written during /auth/login is still readable during /auth/callback.

    Usage in a router:
        @router.get("/example")
        async def example(auth: AuthService = Depends(get_auth_service)):
            ...
    """
    return _get_shared_auth_service()
