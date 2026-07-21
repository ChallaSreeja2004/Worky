"""
app/connectors/github/router.py
==================================
GitHub connector router — PR intelligence endpoint.

ENDPOINTS
---------
  GET  /api/v1/connectors/github/context
       Discover and enrich open PRs for the authenticated user.

DESIGN PRINCIPLES
-----------------
  • The router is thin.  All logic lives in GitHubConnector.
  • GitHubAPIClient is constructed per-request using the token from
    GitHubSettings — AuthService provides the per-user token when available;
    this endpoint accepts ``access_token`` as a query parameter for
    development use and falls back to GITHUB_ACCESS_TOKEN from .env.
  • GitHubError subclasses are mapped to HTTP status codes here.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.connectors.models
  • app.connectors.github.*
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, HTTPException

from app.connectors.models import ConnectorResult
from app.connectors.github.api_client import GitHubAPIClient, GitHubAuthError, GitHubError
from app.connectors.github.connector import GitHubConnector
from app.connectors.github.normalizer import GitHubNormalizer
from app.connectors.github.settings import get_github_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_connector(access_token: str) -> GitHubConnector:
    """Construct a GitHubConnector using the provided token and settings from .env."""
    settings = get_github_settings()
    client = GitHubAPIClient(
        access_token=access_token,
        base_url=settings.github_api_base_url,
        timeout=settings.github_request_timeout,
    )
    return GitHubConnector(
        api_client=client,
        normalizer=GitHubNormalizer(),
        max_prs=settings.github_max_prs,
    )


# ---------------------------------------------------------------------------
# GET /context
# ---------------------------------------------------------------------------

@router.get(
    "/context",
    response_model=ConnectorResult,
    summary="Collect GitHub PR intelligence for the authenticated user",
)
async def get_context(
    access_token: str = Query(
        default="",
        description=(
            "GitHub Personal Access Token or OAuth token.  "
            "When omitted, falls back to GITHUB_ACCESS_TOKEN from .env."
        ),
    ),
) -> ConnectorResult:
    """
    Discovers all open PRs authored by, assigned to, or requesting review
    from the authenticated user, then enriches each with:

    - Full PR metadata (title, description, author, labels, mergeability)
    - Changed files
    - Unified diff (first 2 000 chars)
    - Commits
    - Inline review comments
    - PR reviews (APPROVED / CHANGES_REQUESTED / …)
    - CI check-run results

    Returns a ConnectorResult with status SUCCESS, PARTIAL, or FAILED.

    Status codes
    ------------
    200  — Context collected (check ConnectorResult.status for SUCCESS/PARTIAL/FAILED).
    401  — The GitHub token is invalid or lacks the ``repo`` scope.
    503  — GitHub API is unavailable.
    """
    settings = get_github_settings()
    token = access_token or settings.github_access_token

    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "No GitHub access token provided.  Supply the ``access_token`` "
                "query parameter or set GITHUB_ACCESS_TOKEN in .env."
            ),
        )

    connector = _build_connector(token)

    logger.info("github/context: starting PR intelligence collection")
    try:
        result = await connector.get_context()
    except GitHubAuthError as exc:
        logger.warning("github/context: auth error — %s", exc.message)
        raise HTTPException(status_code=401, detail=exc.message)
    except GitHubError as exc:
        logger.error("github/context: unexpected error — %s", exc.message)
        raise HTTPException(status_code=503, detail=exc.message)

    logger.info(
        "github/context: completed — status=%s prs=%d",
        result.status.value,
        len(result.data.get("pull_requests", [])),
    )
    return result
