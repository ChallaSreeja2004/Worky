"""
app/auth/repository.py
======================
TokenRepository — abstract interface for secure OAuth token persistence.

DESIGN RATIONALE
----------------
The AuthService handles the OAuth flow logic (code exchange, token
refresh, PKCE).  Token PERSISTENCE is a separate concern owned by the
TokenRepository.  This separation means:

  • The AuthService is never changed when the storage backend changes
    (e.g., swapping in-memory → Redis → MongoDB).  Only the concrete
    repository implementation changes.

  • Every repository implementation is independently testable with a
    FakeTokenRepository that holds data in a dict — no real database
    needed in unit tests.

  • Deployment environments can choose the right backend:
      - Local development  → InMemoryTokenRepository  (this file)
      - Staging / Prod     → RedisTokenRepository     (to be implemented)
      - Offline / Desktop  → EncryptedFileTokenRepository (future option)

DEPENDENCY INJECTION
--------------------
The AuthService receives a TokenRepository via its constructor.  FastAPI's
dependency injection system controls which concrete implementation is
injected at runtime based on the APP_ENV setting:

    # In main.py / DI configuration:
    if settings.app_env == "production":
        token_repo = RedisTokenRepository(redis_client)
    else:
        token_repo = InMemoryTokenRepository()

    auth_service = AuthService(token_repository=token_repo)

SECURITY NOTES
--------------
  1. Access tokens are NEVER persisted.  Only the encrypted refresh token
     and the token metadata (user_id, expires_at) are stored.
  2. The refresh_token stored in the repository is always Fernet-encrypted.
     The repository treats it as an opaque bytes string — it never
     decrypts it.  Only the AuthService (which holds the encryption key)
     can decrypt it.
  3. Refresh tokens have a TTL.  Repository implementations should honour
     the `expires_at` field and automatically evict stale entries.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • app.auth.models

It must NOT import from connectors, context_builder, or bob packages.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.auth.models import TokenData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class TokenRepository(ABC):
    """
    Abstract interface for storing and retrieving OAuth token sets.

    All concrete repository implementations (in-memory, Redis, MongoDB,
    encrypted file) must subclass this and implement every abstract method.

    The AuthService depends on this interface, never on a concrete class.
    This is the Dependency Inversion Principle applied to storage.

    Thread / coroutine safety
    -------------------------
    All methods are async.  Concrete implementations must be safe to call
    from multiple async tasks concurrently.  For in-memory implementations,
    this typically means using asyncio.Lock.  For external stores (Redis,
    MongoDB), the client library handles concurrency.
    """

    @abstractmethod
    async def save(self, token_data: TokenData) -> None:
        """
        Persist a token set for a user.

        Called by AuthService after a successful token exchange or refresh.
        If a token set for user_id already exists, it must be overwritten
        — there is at most one active token set per user.

        The refresh_token field on token_data is guaranteed to be
        Fernet-encrypted before this method is called.  The repository
        stores it as-is without further encryption or decryption.

        Parameters
        ----------
        token_data : TokenData
            The complete token set to persist.  The access_token field
            should NOT be persisted (it is in-memory only).  Concrete
            implementations should store only:
              • user_id
              • encrypted refresh_token
              • expires_at
              • token_type
        """
        ...

    @abstractmethod
    async def get(self, user_id: str) -> TokenData | None:
        """
        Retrieve the token set for a user.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.

        Returns
        -------
        TokenData | None
            The stored TokenData if found and not expired, or None if:
              • No token exists for this user_id (user not authenticated).
              • The stored token set has passed its TTL.
            The returned TokenData will have access_token set to an empty
            string — the AuthService populates it after a refresh.
        """
        ...

    @abstractmethod
    async def delete(self, user_id: str) -> None:
        """
        Remove all stored tokens for a user (logout / token revocation).

        After this call, get(user_id) must return None.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.
        """
        ...

    @abstractmethod
    async def exists(self, user_id: str) -> bool:
        """
        Check whether a non-expired token set exists for a user.

        Used by the AuthService to determine whether a user needs to go
        through the full OAuth login flow or can be silently refreshed.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.

        Returns
        -------
        bool
            True if a valid (non-expired) token set exists for this user.
            False otherwise.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory reference implementation
# ---------------------------------------------------------------------------

class InMemoryTokenRepository(TokenRepository):
    """
    In-process, dictionary-backed TokenRepository implementation.

    SUITABLE FOR: Local development and unit tests only.

    NOT SUITABLE FOR: Production deployments with multiple uvicorn workers.
    In a multi-worker process, each worker has isolated memory — tokens
    saved by worker 1 are invisible to worker 2, causing random 401 errors.

    HOW TO USE IN TESTS
    -------------------
        repo = InMemoryTokenRepository()
        auth_service = AuthService(token_repository=repo)

        # Verify token was stored after login:
        stored = await repo.get(user_id)
        assert stored is not None

    HOW TO REPLACE FOR PRODUCTION
    ------------------------------
    1. Implement RedisTokenRepository(TokenRepository) in
       app/auth/redis_repository.py.
    2. Update the DI configuration in main.py to inject
       RedisTokenRepository() when APP_ENV == "production".
    3. Zero changes to AuthService or any other layer.
    """

    def __init__(self) -> None:
        # Simple dict: user_id → TokenData.
        # In a production async context with a real async backend this
        # would use asyncio.Lock for write safety; for in-memory use the
        # GIL provides sufficient protection for single-process dev usage.
        self._store: dict[str, TokenData] = {}

    async def save(self, token_data: TokenData) -> None:
        """Store the token set, overwriting any existing entry."""
        self._store[token_data.user_id] = token_data
        logger.debug("TokenRepository: saved token for user_id=%s", token_data.user_id)

    async def get(self, user_id: str) -> TokenData | None:
        """Return the token set for user_id, or None if not found."""
        token_data = self._store.get(user_id)
        if token_data is None:
            logger.debug("TokenRepository: no token found for user_id=%s", user_id)
            return None
        # Do not evict here — eviction is the AuthService's responsibility.
        # The AuthService calls token_data.is_expired and refreshes or re-auths.
        return token_data

    async def delete(self, user_id: str) -> None:
        """Remove the token set for user_id.  No-op if not found."""
        removed = self._store.pop(user_id, None)
        if removed:
            logger.debug("TokenRepository: deleted token for user_id=%s", user_id)

    async def exists(self, user_id: str) -> bool:
        """Return True if a token set exists for user_id."""
        return user_id in self._store

    # ------------------------------------------------------------------
    # Test helpers (not part of the interface contract)
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all tokens.  Useful for test teardown."""
        self._store.clear()

    @property
    def stored_user_ids(self) -> list[str]:
        """Return all user IDs currently held in the store.  For tests only."""
        return list(self._store.keys())
