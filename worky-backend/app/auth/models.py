"""
app/auth/models.py
==================
Pydantic models for the Worky authentication layer.

These models represent the OAuth token lifecycle and the data returned
to the desktop client after a successful login.  They are shared across
the auth router, auth service, and all TokenRepository implementations.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • Pydantic

It must NOT import from connectors, context_builder, or bob packages.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field


class TokenData(BaseModel):
    """
    The complete OAuth token set for a single authenticated user.

    This is the object stored and retrieved by every TokenRepository
    implementation.  The refresh_token field is ALWAYS stored in
    encrypted form — the TokenRepository is responsible for receiving
    an already-encrypted value and returning it as-is.  Decryption is
    performed exclusively inside the AuthService.

    Fields
    ------
    user_id : str
        Microsoft user object ID (the `oid` claim from the id_token JWT).
        This is the canonical user identifier across all connectors.

    access_token : str
        Short-lived (1 hour) bearer token used to call enterprise APIs.
        Stored in memory only — never persisted to disk or database.

    refresh_token : str
        Long-lived encrypted token used to obtain new access tokens
        without re-prompting the user.  Always Fernet-encrypted before
        being passed to the repository.

    expires_at : datetime
        UTC datetime when the access_token expires.  The AuthService
        checks this before every API call and proactively refreshes
        if fewer than TOKEN_REFRESH_BUFFER_MINUTES remain.

    token_type : str
        Always "Bearer" for Microsoft Graph.  Included for completeness
        and forward compatibility.
    """

    # How many minutes before expiry to proactively refresh the token.
    # Defined here as a class constant so it is easy to find and change.
    TOKEN_REFRESH_BUFFER_MINUTES: int = 5

    user_id: str = Field(..., description="Microsoft user object ID.")
    access_token: str = Field(..., description="Bearer token for enterprise API calls.")
    refresh_token: str = Field(..., description="Encrypted refresh token.")
    expires_at: datetime = Field(..., description="UTC expiry datetime of the access token.")
    token_type: str = Field(default="Bearer")

    @property
    def is_expired(self) -> bool:
        """
        True if the access token has expired or will expire within the
        refresh buffer window (default: 5 minutes).

        The AuthService uses this before every connector API call to
        decide whether a silent token refresh is needed.
        """
        buffer = timedelta(minutes=self.TOKEN_REFRESH_BUFFER_MINUTES)
        return datetime.now(timezone.utc) >= (self.expires_at - buffer)


class AuthorizationResponse(BaseModel):
    """
    Payload returned to the Worky desktop client after a successful OAuth
    login and token exchange.

    Only non-sensitive fields are included here.  The access_token is
    returned so the desktop client can make immediate API calls, but the
    refresh_token is NEVER sent to the client — it is stored server-side
    by the TokenRepository.

    Fields
    ------
    user_id : str
        The Worky-internal user identifier.

    display_name : str
        The user's full name from their enterprise directory profile.

    email : str
        The user's enterprise email address.

    access_token : str
        A valid access token the desktop client can use immediately.

    expires_at : datetime
        When the access token expires.  The desktop client can use this
        to decide when to re-authenticate (though silent refresh is
        handled server-side automatically).
    """

    user_id: str
    display_name: str
    email: str
    access_token: str
    expires_at: datetime
