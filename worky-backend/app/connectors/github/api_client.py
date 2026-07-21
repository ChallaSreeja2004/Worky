"""
app/connectors/github/api_client.py
=====================================
GitHubAPIClient — async HTTP abstraction for the GitHub REST API.

RESPONSIBILITIES
----------------
  • Attach Authorization: Bearer <token> and Accept: application/vnd.github+json
    headers on every request.
  • Centralise all GitHub REST API HTTP communication for the GitHub connector.
  • Retry transient failures (HTTP 429, HTTP 503) with exponential back-off.
  • Raise typed, GitHub-specific exceptions so callers can react precisely.
  • Return raw GitHub API JSON — no normalisation, no transformation.

WHAT THIS CLIENT DOES NOT DO
------------------------------
  • It does NOT refresh tokens — the caller provides a valid token.
  • It does NOT know about ConnectorResult, WorkContext, or IBM Bob.
  • It does NOT normalise or interpret GitHub responses.
  • It does NOT cache responses.
  • It does NOT contain business logic.

RETRY POLICY
------------
Only HTTP 429 (Too Many Requests) and HTTP 503 (Service Unavailable) trigger
retries — these are transient load conditions.

  Attempt 1 → failure → wait 1 s
  Attempt 2 → failure → wait 2 s
  Attempt 3 → failure → raise GitHubRateLimitError  (429 / 503)
                       raise GitHubServiceError      (timeout / network)

All other non-2xx responses (401, 403, 404, 422, 500 …) are raised
immediately without retrying.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • httpx

It must NOT import from:
  • app.auth
  • app.config
  • app.connectors.base
  • app.connectors.models
  • app.context_builder
  • any other app module
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES: int = 3
_RETRY_BACK_OFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 503})

# GitHub REST API requires this Accept header for all v3 endpoints.
_GITHUB_JSON_ACCEPT = "application/vnd.github+json"
# Special accept header to retrieve a PR diff body.
_GITHUB_DIFF_ACCEPT = "application/vnd.github.diff"


# ---------------------------------------------------------------------------
# GitHubAPIClient
# ---------------------------------------------------------------------------

class GitHubAPIClient:
    """
    Authenticated, async HTTP client for the GitHub REST API.

    Designed to be instantiated once per connector execution cycle and
    discarded afterwards.

    Parameters
    ----------
    access_token : str
        A valid GitHub Personal Access Token (PAT) with ``repo`` scope, or
        a delegated OAuth token from a GitHub OAuth App.
    base_url : str
        API base URL.  Defaults to https://api.github.com.  Override for
        GitHub Enterprise Server deployments.
    timeout : float
        Per-request timeout in seconds.  Defaults to 20.0 s.
    """

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.github.com",
        timeout: float = 20.0,
    ) -> None:
        self._access_token = access_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {access_token}",
            "Accept": _GITHUB_JSON_ACCEPT,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Public API — discovery
    # ------------------------------------------------------------------

    async def search_pull_requests(self, query: str) -> dict[str, Any]:
        """
        Search for pull requests matching a GitHub search query.

        GitHub API endpoint:
            GET /search/issues?q=<query>&type=pullrequest

        The default query used by GitHubConnector:
            ``is:open is:pr (author:@me OR review-requested:@me OR assignee:@me)``

        Required scope: ``repo`` (or ``public_repo`` for public repos only).

        Parameters
        ----------
        query : str
            GitHub issues/PRs search query string.

        Returns
        -------
        dict
            Raw GitHub search response.  Relevant fields:
              total_count  — total number of matching items
              items        — list of issue/PR objects (each has ``number``,
                             ``repository_url``, ``title``, ``html_url``, …)

        Raises
        ------
        GitHubAuthError
            On 401 or 403.
        GitHubRateLimitError
            On 429 / 503 after all retries.
        GitHubServiceError
            On any other error.
        """
        return await self._get("/search/issues", params={"q": query, "per_page": "100"})

    # ------------------------------------------------------------------
    # Public API — PR detail fetches
    # ------------------------------------------------------------------

    async def get_pull_request(
        self, owner: str, repo: str, number: int
    ) -> dict[str, Any]:
        """
        Fetch full PR metadata.

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/pulls/{pull_number}

        Returns
        -------
        dict
            Raw GitHub PullRequest object.  Relevant fields:
              number, title, body, state, html_url, draft, mergeable,
              head (sha, ref), base (ref), user (login), labels,
              created_at, updated_at, requested_reviewers, assignees.
        """
        return await self._get(f"/repos/{owner}/{repo}/pulls/{number}")

    async def get_pull_request_files(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all files changed in a PR.

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/pulls/{pull_number}/files

        Returns
        -------
        list[dict]
            List of raw file objects.  Each contains:
              filename, status, additions, deletions, changes.
        """
        result = await self._get(
            f"/repos/{owner}/{repo}/pulls/{number}/files",
            params={"per_page": "100"},
        )
        # GitHub returns a list directly for this endpoint, not a dict.
        if isinstance(result, list):
            return result
        # Defensive: if wrapped, extract items.
        return result.get("files", result.get("items", []))  # type: ignore[return-value]

    async def get_pull_request_diff(
        self, owner: str, repo: str, number: int
    ) -> str:
        """
        Fetch the unified diff for a PR as plain text.

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/pulls/{pull_number}
            Accept: application/vnd.github.diff

        Returns
        -------
        str
            Raw unified diff text.  May be very large for big PRs.
            The normalizer is responsible for truncating this.
        """
        return await self._get_raw(
            f"/repos/{owner}/{repo}/pulls/{number}",
            accept=_GITHUB_DIFF_ACCEPT,
        )

    async def get_pull_request_commits(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all commits in a PR.

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/pulls/{pull_number}/commits

        Returns
        -------
        list[dict]
            List of raw commit objects.  Each contains sha, commit.message,
            author, committer.
        """
        result = await self._get(
            f"/repos/{owner}/{repo}/pulls/{number}/commits",
            params={"per_page": "100"},
        )
        if isinstance(result, list):
            return result
        return result.get("commits", result.get("items", []))  # type: ignore[return-value]

    async def get_review_comments(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """
        Fetch inline review comments (line-level) for a PR.

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/pulls/{pull_number}/comments

        Returns
        -------
        list[dict]
            List of raw review comment objects.  Each contains:
              id, user.login, body, path, created_at, updated_at.
        """
        result = await self._get(
            f"/repos/{owner}/{repo}/pulls/{number}/comments",
            params={"per_page": "100"},
        )
        if isinstance(result, list):
            return result
        return result.get("comments", result.get("items", []))  # type: ignore[return-value]

    async def get_pull_request_reviews(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """
        Fetch top-level PR reviews (APPROVED, CHANGES_REQUESTED, etc.).

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews

        Returns
        -------
        list[dict]
            List of raw review objects.  Each contains:
              id, user.login, state, body, submitted_at.
        """
        result = await self._get(
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            params={"per_page": "100"},
        )
        if isinstance(result, list):
            return result
        return result.get("reviews", result.get("items", []))  # type: ignore[return-value]

    async def get_check_runs(
        self, owner: str, repo: str, ref: str
    ) -> dict[str, Any]:
        """
        Fetch CI check-runs for a given commit SHA.

        GitHub API endpoint:
            GET /repos/{owner}/{repo}/commits/{ref}/check-runs

        Parameters
        ----------
        ref : str
            The commit SHA (typically ``head.sha`` from the PR object).

        Returns
        -------
        dict
            Raw check-runs response.  Relevant fields:
              total_count, check_runs (list of check run objects, each with:
              name, status, conclusion, started_at, completed_at).
        """
        return await self._get(
            f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
            params={"per_page": "100"},
        )

    async def get_authenticated_user(self) -> dict[str, Any]:
        """
        Fetch the authenticated user's profile.

        GitHub API endpoint:
            GET /user

        Returns
        -------
        dict
            Raw user object.  Relevant field: ``login`` (username).
        """
        return await self._get("/user")

    async def ping(self) -> bool:
        """
        Verify that the GitHub API is reachable and the token is valid.

        Calls GET /user and returns True on success.  Returns False on any
        failure without raising — used by GitHubConnector.health_check().

        Returns
        -------
        bool
            True  — GitHub API responded successfully.
            False — Any error occurred (network, invalid token, …).
        """
        try:
            await self.get_authenticated_user()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHubAPIClient.ping: health check failed — %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal HTTP layer
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> Any:
        """
        Execute a GET request against the GitHub REST API with retry logic.

        Returns the parsed JSON body (dict or list depending on the endpoint).

        Raises
        ------
        GitHubAuthError
            On HTTP 401 or 403.
        GitHubRateLimitError
            On HTTP 429 or 503 after all retry attempts are exhausted.
        GitHubServiceError
            On any other non-2xx or network/timeout failure.
        """
        return await self._request(path, params=params, accept=_GITHUB_JSON_ACCEPT)

    async def _get_raw(self, path: str, accept: str) -> str:
        """
        Execute a GET request and return the raw response body as a string.

        Used for the diff endpoint which returns text/plain rather than JSON.
        """
        url = f"{self._base_url}{path}"
        headers = {**self._headers, "Accept": accept}

        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as client:
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    response = await client.get(url)
                except httpx.RequestError as exc:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACK_OFF_SECONDS[attempt - 1]
                        logger.warning(
                            "GitHubAPIClient: %s on %s (attempt %d/%d) — retrying in %.1f s",
                            type(exc).__name__, path, attempt, _MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise GitHubServiceError(
                        f"Network error calling GitHub API {path!r}: {exc}"
                    ) from exc

                if response.status_code == 200:
                    return response.text

                if response.status_code in (401, 403):
                    raise GitHubAuthError(
                        f"GitHub API returned {response.status_code} on {path!r}: "
                        f"{response.text[:200]}"
                    )

                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACK_OFF_SECONDS[attempt - 1]
                        await asyncio.sleep(wait)
                        continue
                    raise GitHubRateLimitError(
                        f"GitHub API returned {response.status_code} on {path!r} "
                        f"after {_MAX_RETRIES} attempts."
                    )

                raise GitHubServiceError(
                    f"GitHub API returned {response.status_code} on {path!r}: "
                    f"{response.text[:200]}"
                )

        raise GitHubServiceError(  # pragma: no cover
            f"GitHub API call to {path!r} failed after {_MAX_RETRIES} attempts."
        )

    async def _request(
        self,
        path: str,
        params: dict[str, str] | None = None,
        accept: str = _GITHUB_JSON_ACCEPT,
    ) -> Any:
        """Core GET-with-retry implementation that returns parsed JSON."""
        url = f"{self._base_url}{path}"
        headers = {**self._headers, "Accept": accept}

        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as client:
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    response = await client.get(url, params=params)

                except httpx.RequestError as exc:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACK_OFF_SECONDS[attempt - 1]
                        logger.warning(
                            "GitHubAPIClient: %s on %s (attempt %d/%d) — retrying in %.1f s",
                            type(exc).__name__, path, attempt, _MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    if isinstance(exc, httpx.TimeoutException):
                        raise GitHubServiceError(
                            f"Request to GitHub API {path!r} timed out after "
                            f"{_MAX_RETRIES} attempts."
                        ) from exc
                    raise GitHubServiceError(
                        f"Network error calling GitHub API {path!r}: {exc}"
                    ) from exc

                if response.status_code == 200:
                    return response.json()

                if response.status_code in (401, 403):
                    detail = _extract_error_message(response)
                    logger.error(
                        "GitHubAPIClient: auth failure %d on %s — %s",
                        response.status_code, path, detail,
                    )
                    raise GitHubAuthError(
                        f"GitHub API returned {response.status_code} on {path!r}: "
                        f"{detail}"
                    )

                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACK_OFF_SECONDS[attempt - 1]
                        logger.warning(
                            "GitHubAPIClient: %d on %s (attempt %d/%d) — retrying in %.1f s",
                            response.status_code, path, attempt, _MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise GitHubRateLimitError(
                        f"GitHub API returned {response.status_code} on {path!r} "
                        f"after {_MAX_RETRIES} attempts."
                    )

                detail = _extract_error_message(response)
                logger.error(
                    "GitHubAPIClient: unexpected %d on %s — %s",
                    response.status_code, path, detail,
                )
                raise GitHubServiceError(
                    f"GitHub API returned {response.status_code} on {path!r}: "
                    f"{detail}"
                )

        raise GitHubServiceError(  # pragma: no cover
            f"GitHub API call to {path!r} failed after {_MAX_RETRIES} attempts."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_error_message(response: httpx.Response) -> str:
    """
    Extract a human-readable error message from a GitHub error response body.

    GitHub error responses follow the schema:
        {"message": "...", "documentation_url": "..."}

    Falls back to ``response.text[:200]`` when parsing fails or the
    ``message`` field is absent.
    """
    try:
        body = response.json()
        return body.get("message") or response.text[:200]
    except Exception:  # noqa: BLE001
        return response.text[:200]


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class GitHubError(Exception):
    """
    Base class for all GitHub API errors raised by GitHubAPIClient.

    All GitHub-specific exceptions inherit from this class so callers can
    catch ``GitHubError`` in a single clause when they do not need to
    distinguish between failure modes.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class GitHubAuthError(GitHubError):
    """
    Raised on HTTP 401 Unauthorized or 403 Forbidden from the GitHub API.

    Indicates the token is invalid, expired, or lacks the required scope.
    """


class GitHubRateLimitError(GitHubError):
    """
    Raised on HTTP 429 Too Many Requests or 503 Service Unavailable after
    all retry attempts are exhausted.
    """


class GitHubServiceError(GitHubError):
    """
    Raised on any other non-2xx response, network error, or timeout.

    Covers: 404, 422, 500, 502, network timeouts, DNS failures, etc.
    """
