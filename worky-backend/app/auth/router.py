"""
app/auth/router.py
==================
Authentication router — Microsoft OAuth 2.0 endpoints.

ENDPOINTS
---------
  GET  /api/v1/auth/login      — generate Microsoft authorization URL
  GET  /api/v1/auth/callback   — exchange authorization code for tokens
  POST /api/v1/auth/refresh    — refresh an expired access token

DESIGN PRINCIPLES
-----------------
  • Routers are thin.  All business logic lives in AuthService.
  • AuthService is never instantiated here — it is injected via FastAPI's
    Depends() mechanism, using the providers in app.auth.dependencies.
  • Error types raised by AuthService are mapped to the correct HTTP status
    codes here so the service layer stays HTTP-agnostic.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.auth.service    (for exception types)
  • app.auth.models     (for response types)
  • app.auth.dependencies
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.auth.dependencies import get_auth_service
from app.auth.models import AuthorizationResponse
from app.auth.service import (
    AuthCodeExchangeError,
    AuthRefreshError,
    AuthService,
    AuthStateError,
    AuthUserNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /login
# ---------------------------------------------------------------------------

@router.get(
    "/login",
    summary="Initiate Microsoft OAuth login",
    description=(
        "Generates a PKCE code_verifier/challenge pair and a secure state "
        "parameter, then redirects the browser to the Microsoft login page."
    ),
    response_class=RedirectResponse,
    status_code=302,
)
def login(
    auth_service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """
    Redirect the user to the Microsoft authorization endpoint.

    The PKCE verifier and state are stored in-process and consumed when
    the user returns to /callback.  This endpoint is synchronous because
    URL generation involves no I/O.
    """
    authorization_url, state = auth_service.get_authorization_url()
    logger.info("auth/login: redirecting to Microsoft (state=%s)", state)
    return RedirectResponse(url=authorization_url, status_code=302)


# ---------------------------------------------------------------------------
# GET /callback
# ---------------------------------------------------------------------------

@router.get(
    "/callback",
    response_model=AuthorizationResponse,
    summary="Handle Microsoft OAuth callback",
    description=(
        "Validates the state parameter, exchanges the authorization code for "
        "an access token and refresh token, stores tokens securely, and returns "
        "the AuthorizationResponse to the desktop client."
    ),
)
async def callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="State parameter for CSRF validation"),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthorizationResponse:
    """
    Handle the OAuth 2.0 callback from Microsoft.

    Microsoft redirects here after the user authenticates.  This endpoint
    validates the state, exchanges the code for tokens, and returns the
    AuthorizationResponse to the client.

    Raises HTTP 400 if the state is invalid (CSRF protection).
    Raises HTTP 502 if Microsoft's token endpoint fails.
    """
    try:
        auth_response = await auth_service.exchange_code_for_tokens(
            code=code, state=state
        )
    except AuthStateError as exc:
        logger.warning("auth/callback: invalid state — %s", exc.message)
        raise HTTPException(status_code=400, detail=exc.message)
    except AuthCodeExchangeError as exc:
        logger.error("auth/callback: code exchange failed — %s", exc.message)
        raise HTTPException(status_code=502, detail=exc.message)

    logger.info(
        "auth/callback: authentication successful for user_id=%s",
        auth_response.user_id,
    )
    return auth_response


# ---------------------------------------------------------------------------
# POST /refresh
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=AuthorizationResponse,
    summary="Refresh an expired access token",
    description=(
        "Silently exchanges the stored refresh token for a new access token "
        "and returns an updated AuthorizationResponse."
    ),
)
async def refresh(
    user_id: str = Query(..., description="Worky-internal user identifier"),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthorizationResponse:
    """
    Refresh the access token for the given user.

    Calls AuthService.get_valid_token() which handles the silent refresh
    internally.  Returns a fresh AuthorizationResponse with the new token.

    Raises HTTP 401 if the user is not authenticated or the refresh token
    has expired at Microsoft.
    Raises HTTP 500 if decryption of the stored refresh token fails.
    """
    try:
        access_token = await auth_service.get_valid_token(user_id=user_id)
    except AuthUserNotFoundError as exc:
        logger.warning("auth/refresh: user not found — %s", exc.message)
        raise HTTPException(status_code=401, detail=exc.message)
    except AuthRefreshError as exc:
        logger.error("auth/refresh: refresh failed — %s", exc.message)
        raise HTTPException(status_code=401, detail=exc.message)

    # Retrieve the updated token_data to build the response.
    token_data = await auth_service.get_token_data(user_id)

    logger.info("auth/refresh: token refreshed for user_id=%s", user_id)
    return AuthorizationResponse(
        user_id=user_id,
        display_name="",   # display_name is not re-fetched on refresh
        email="",          # email is not re-fetched on refresh
        access_token=access_token,
        expires_at=token_data.expires_at,
    )
