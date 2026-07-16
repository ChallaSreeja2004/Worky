"""
app/auth/service.py
===================
AuthService — Microsoft OAuth 2.0 Authorization Code Flow with PKCE.

RESPONSIBILITIES
----------------
  • Generate PKCE code_verifier / code_challenge pairs
  • Generate cryptographically random state parameters for CSRF protection
  • Build the Microsoft authorization URL the user is redirected to
  • Exchange the authorization code for an access_token + refresh_token
  • Encrypt the refresh_token before handing it to TokenRepository
  • Silently refresh an expired access_token using the stored refresh_token
  • Return a valid access_token to any caller (Phase 3 Graph Client will use this)
  • Revoke stored tokens on logout

WHAT THIS SERVICE DOES NOT DO
------------------------------
  • It does NOT call Microsoft Graph (that begins in Phase 3)
  • It does NOT know about connectors, WorkContext, or IBM Bob
  • It does NOT choose which TokenRepository implementation to use —
    the concrete repository is injected via the constructor

PKCE SECURITY NOTE
------------------
PKCE (Proof Key for Code Exchange) eliminates the need for a client secret
in public/desktop clients.  For each login attempt a fresh random
code_verifier is generated, and code_challenge = BASE64URL(SHA256(verifier))
is sent with the authorization request.  When the callback returns with an
authorization code, we prove we initiated the request by sending the original
verifier.  An interceptor who only has the authorization code cannot redeem
it without the verifier.

JWT CLAIMS NOTE
---------------
The id_token returned by Microsoft is decoded to extract user identity
claims (oid, name, preferred_username).  We do NOT verify the JWT signature
here — the token is received directly over HTTPS from Microsoft's token
endpoint, which is the trust anchor.  This avoids the python-jose dependency
and is sufficient for extracting display metadata from a trusted source.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • httpx
  • cryptography
  • app.auth.models
  • app.auth.repository
  • app.config.settings
  • app.connectors.outlook.settings

It must NOT import from context_builder, connectors data layer, or bob.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.auth.models import AuthorizationResponse, TokenData
from app.auth.repository import TokenRepository
from app.config.settings import get_settings
from app.connectors.outlook.settings import get_outlook_settings

logger = logging.getLogger(__name__)


class AuthService:
    """
    Manages the Microsoft OAuth 2.0 Authorization Code + PKCE flow.

    This service is stateless with respect to token storage — it delegates
    all persistence to the injected TokenRepository.  The only transient
    state it holds is the in-process PKCE verifier map, which lives only
    for the duration of a single login redirect round-trip.

    Parameters
    ----------
    token_repository : TokenRepository
        The storage backend for OAuth tokens.  In development this is
        InMemoryTokenRepository; in production it will be a persistent
        implementation.  The service is unaware of which concrete
        implementation is used.
    """

    def __init__(self, token_repository: TokenRepository) -> None:
        self._repo = token_repository
        self._settings = get_settings()
        self._outlook = get_outlook_settings()
        self._fernet = Fernet(self._settings.token_encryption_key.encode())

        # Transient in-process map: state → code_verifier.
        # Populated in get_authorization_url(), consumed (and removed) in
        # exchange_code_for_tokens().  Each entry lives for one login round-trip.
        # In a multi-process deployment this map would need to move to Redis,
        # but for a single-worker desktop backend it is sufficient.
        self._pkce_store: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Step 1 — Build the Microsoft authorization URL
    # ------------------------------------------------------------------

    def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate the Microsoft login URL the user must visit to authenticate.

        Creates a fresh PKCE pair and a random state parameter on every
        call so that each login attempt is cryptographically independent.

        Returns
        -------
        (authorization_url, state)
            authorization_url — redirect the browser / Electron window here.
            state             — store this and verify it in the callback.
        """
        state = self._generate_state()
        code_verifier, code_challenge = self._generate_pkce_pair()

        # Persist the verifier so exchange_code_for_tokens() can retrieve it.
        self._pkce_store[state] = code_verifier
        logger.info("AuthService: generated authorization URL (state=%s)", state)

        params = {
            "client_id":             self._outlook.outlook_client_id,
            "response_type":         "code",
            "redirect_uri":          self._outlook.outlook_redirect_uri,
            "scope":                 self._outlook.scopes_str,
            "state":                 state,
            "code_challenge":        code_challenge,
            "code_challenge_method": "S256",
            "response_mode":         "query",
            "prompt":                "select_account",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self._outlook.authorize_url}?{query_string}"
        return url, state

    # ------------------------------------------------------------------
    # Step 2 — Exchange authorization code for tokens
    # ------------------------------------------------------------------

    async def exchange_code_for_tokens(
        self, code: str, state: str
    ) -> AuthorizationResponse:
        """
        Exchange the authorization code received in the OAuth callback for
        an access_token and refresh_token.

        Parameters
        ----------
        code : str
            The authorization code from Microsoft's callback query string.
        state : str
            The state parameter from the callback.  Must match a value
            previously returned by get_authorization_url().

        Returns
        -------
        AuthorizationResponse
            User identity and access token returned to the desktop client.
            The refresh_token is NOT included — it is stored server-side.

        Raises
        ------
        AuthStateError
            If the state parameter is unknown.  Indicates a CSRF attempt or
            an expired / replayed login session.
        AuthCodeExchangeError
            If Microsoft returns an error during token exchange, or if a
            network failure prevents reaching the token endpoint.
        """
        code_verifier = self._pkce_store.pop(state, None)
        if code_verifier is None:
            logger.warning(
                "AuthService: unknown state parameter '%s' — possible CSRF", state
            )
            raise AuthStateError(
                "Unknown or expired state parameter. "
                "Please restart the login flow."
            )

        payload = {
            "client_id":     self._outlook.outlook_client_id,
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  self._outlook.outlook_redirect_uri,
            "code_verifier": code_verifier,
        }

        raw = await self._post_token_request(payload)
        token_data, display_name, email = self._build_token_data(raw)

        await self._repo.save(token_data)
        logger.info(
            "AuthService: tokens stored for user_id=%s display_name=%s",
            token_data.user_id,
            display_name,
        )

        return AuthorizationResponse(
            user_id=token_data.user_id,
            display_name=display_name,
            email=email,
            access_token=token_data.access_token,
            expires_at=token_data.expires_at,
        )

    # ------------------------------------------------------------------
    # Step 3 — Get a valid access token (refresh silently if needed)
    # ------------------------------------------------------------------

    async def get_valid_token(self, user_id: str) -> str:
        """
        Return a valid access token for the given user.

        If the stored token is expired or within the 5-minute refresh buffer
        defined in TokenData.TOKEN_REFRESH_BUFFER_MINUTES, the token is
        silently refreshed before returning.

        This is the method Phase 3 (GraphAPIClient) will call.  It never
        needs to know whether a refresh happened.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.

        Returns
        -------
        str
            A valid, unexpired access token.

        Raises
        ------
        AuthUserNotFoundError
            If no token exists for this user_id.  The caller should
            redirect the user through the login flow.
        AuthRefreshError
            If the refresh token is invalid or has expired at Microsoft.
        """
        token_data = await self._repo.get(user_id)
        if token_data is None:
            raise AuthUserNotFoundError(
                f"No token found for user_id={user_id!r}. "
                "User must authenticate first."
            )

        if token_data.is_expired:
            logger.info(
                "AuthService: access token expired for user_id=%s — refreshing",
                user_id,
            )
            try:
                token_data = await self._refresh_token(token_data)
            except AuthCodeExchangeError as exc:
                raise AuthRefreshError(
                    f"Token refresh failed — please log in again. ({exc.message})"
                ) from exc
            await self._repo.save(token_data)

        return token_data.access_token

    # ------------------------------------------------------------------
    # Token refresh (internal)
    # ------------------------------------------------------------------

    async def _refresh_token(self, token_data: TokenData) -> TokenData:
        """
        Exchange a stored encrypted refresh_token for a new token set.

        The existing token_data.user_id is preserved as a fallback if
        Microsoft does not return a new id_token on the refresh response.

        Raises
        ------
        AuthRefreshError
            If decryption of the stored refresh token fails (e.g., the
            TOKEN_ENCRYPTION_KEY was rotated).
        AuthCodeExchangeError
            If Microsoft's token endpoint returns an error.
        """
        try:
            decrypted_refresh = self._decrypt(token_data.refresh_token)
        except AuthEncryptionError as exc:
            raise AuthRefreshError(
                "Failed to decrypt stored refresh token. "
                "The TOKEN_ENCRYPTION_KEY may have been rotated."
            ) from exc

        payload = {
            "client_id":     self._outlook.outlook_client_id,
            "grant_type":    "refresh_token",
            "refresh_token": decrypted_refresh,
            "scope":         self._outlook.scopes_str,
        }

        raw = await self._post_token_request(payload)

        # On a refresh response Microsoft may not return a new id_token.
        # Pass the existing user_id as a fallback so the record stays stable.
        new_token_data, _, _ = self._build_token_data(
            raw, fallback_user_id=token_data.user_id
        )

        logger.info(
            "AuthService: token refreshed for user_id=%s", new_token_data.user_id
        )
        return new_token_data

    # ------------------------------------------------------------------
    # Logout / revocation
    # ------------------------------------------------------------------

    async def get_token_data(self, user_id: str) -> TokenData | None:
        """
        Return the stored TokenData for a user, or None if not found.

        Used by the router to read expires_at after a successful refresh
        without accessing the repository directly.
        """
        return await self._repo.get(user_id)

    async def revoke_token(self, user_id: str) -> None:
        """
        Remove all stored tokens for a user (logout).

        This removes our copy of the refresh token.  The user will need
        to log in again to obtain new tokens.

        Parameters
        ----------
        user_id : str
            The Worky-internal user identifier.
        """
        await self._repo.delete(user_id)
        logger.info("AuthService: tokens revoked for user_id=%s", user_id)

    # ------------------------------------------------------------------
    # HTTP helper — all token endpoint calls go through here
    # ------------------------------------------------------------------

    async def _post_token_request(self, payload: dict) -> dict:
        """
        POST to Microsoft's token endpoint and return the parsed JSON body.

        Raises
        ------
        AuthCodeExchangeError
            On any non-2xx response or network failure.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    self._outlook.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as exc:
            raise AuthCodeExchangeError(
                f"Network error contacting Microsoft token endpoint: {exc}"
            ) from exc

        if response.status_code != 200:
            try:
                error_body = response.json()
                error_desc = error_body.get(
                    "error_description", response.text[:200]
                )
            except Exception:
                error_desc = response.text[:200]

            logger.error(
                "AuthService: token endpoint returned %s — %s",
                response.status_code,
                error_desc,
            )
            raise AuthCodeExchangeError(
                f"Microsoft token endpoint returned {response.status_code}: "
                f"{error_desc}"
            )

        return response.json()

    # ------------------------------------------------------------------
    # Token data builder
    # ------------------------------------------------------------------

    def _build_token_data(
        self,
        raw: dict,
        fallback_user_id: str = "",
    ) -> Tuple[TokenData, str, str]:
        """
        Build a TokenData instance from a raw Microsoft token response.

        Parameters
        ----------
        raw : dict
            Parsed JSON body from Microsoft's token endpoint.
        fallback_user_id : str
            Used when raw does not contain an id_token (e.g. on refresh).

        Returns
        -------
        (TokenData, display_name, email)
        """
        user_id, display_name, email = self._extract_id_token_claims(
            raw.get("id_token", ""), fallback_user_id
        )

        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(raw.get("expires_in", 3600))
        )

        encrypted_refresh = self._encrypt(raw["refresh_token"])

        token_data = TokenData(
            user_id=user_id,
            access_token=raw["access_token"],
            refresh_token=encrypted_refresh,
            expires_at=expires_at,
        )
        return token_data, display_name, email

    # ------------------------------------------------------------------
    # id_token claims extraction
    # ------------------------------------------------------------------

    def _extract_id_token_claims(
        self, id_token: str, fallback_user_id: str
    ) -> Tuple[str, str, str]:
        """
        Decode the id_token JWT payload to extract user identity claims.

        We perform NO signature verification — we trust Microsoft's HTTPS
        response as the trust anchor.  The id_token is used only to extract
        user metadata (oid, name, email) for display purposes and as a
        stable user identifier.

        Returns
        -------
        (user_id, display_name, email)
        """
        if not id_token:
            return fallback_user_id or "unknown", "", ""

        try:
            parts = id_token.split(".")
            if len(parts) < 2:
                raise ValueError("Malformed JWT — expected at least 2 segments")

            # Add base64 padding if necessary (JWT strips padding)
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            claims = json.loads(base64.urlsafe_b64decode(payload_b64))

            user_id = (
                claims.get("oid")      # Azure AD object ID — most stable identifier
                or claims.get("sub")   # subject claim — fallback
                or fallback_user_id
                or "unknown"
            )
            display_name = claims.get("name", "")
            email = (
                claims.get("preferred_username")
                or claims.get("email")
                or claims.get("upn")
                or ""
            )
            return user_id, display_name, email

        except Exception as exc:
            logger.warning(
                "AuthService: could not parse id_token claims — %s", exc
            )
            return fallback_user_id or "unknown", "", ""

    # ------------------------------------------------------------------
    # PKCE helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_pkce_pair() -> Tuple[str, str]:
        """
        Generate a (code_verifier, code_challenge) pair for PKCE.

        code_verifier  — 64 random bytes, base64url-encoded (no padding)
        code_challenge — BASE64URL(SHA256(ASCII(code_verifier)))  [S256 method]
        """
        verifier_bytes = os.urandom(64)
        code_verifier = (
            base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")
        )
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = (
            base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        )
        return code_verifier, code_challenge

    @staticmethod
    def _generate_state() -> str:
        """
        Generate a random, opaque state parameter for CSRF protection.

        32 bytes → 256 bits of entropy.  Statistically impossible to guess;
        unique across all concurrent login attempts.
        """
        return (
            base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
        )

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    def _encrypt(self, plaintext: str) -> str:
        """Fernet-encrypt a plaintext string. Returns a base64 ciphertext string."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a Fernet ciphertext string.

        Raises
        ------
        AuthEncryptionError
            If decryption fails (wrong key, tampered data, truncated token).
        """
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except (InvalidToken, Exception) as exc:
            raise AuthEncryptionError(
                "Refresh token decryption failed. "
                "The TOKEN_ENCRYPTION_KEY may have been rotated."
            ) from exc


# ---------------------------------------------------------------------------
# Auth-specific exception hierarchy
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Base class for all authentication errors raised by AuthService."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AuthStateError(AuthError):
    """
    Raised when the OAuth state parameter is unknown or has expired.

    Indicates a possible CSRF attack or a stale login attempt.
    The router maps this to HTTP 400.
    """


class AuthCodeExchangeError(AuthError):
    """
    Raised when Microsoft's token endpoint returns an error or is unreachable.

    The router maps this to HTTP 502 Bad Gateway.
    """


class AuthRefreshError(AuthError):
    """
    Raised when a token refresh fails — the refresh token may be expired
    or revoked.  The user must re-authenticate.

    The router maps this to HTTP 401 Unauthorized.
    """


class AuthUserNotFoundError(AuthError):
    """
    Raised when get_valid_token() is called for a user who has not
    authenticated.  The caller should redirect to the login flow.

    The router maps this to HTTP 401 Unauthorized.
    """


class AuthEncryptionError(AuthError):
    """
    Raised when Fernet decryption of a stored refresh token fails.

    Usually caused by a rotated TOKEN_ENCRYPTION_KEY.
    The router maps this to HTTP 500 Internal Server Error.
    """
