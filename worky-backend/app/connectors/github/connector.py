"""
app/connectors/github/connector.py
=====================================
GitHubConnector — BaseConnector implementation for GitHub.

RESPONSIBILITIES
----------------
  • Implement the BaseConnector interface for the GitHub enterprise application.
  • Accept a pre-built GitHubAPIClient and GitHubNormalizer via constructor injection.
  • Search for open PRs authored by, assigned to, or requesting review from the user.
  • For each discovered PR, run all enrichment sub-fetches concurrently via asyncio.gather().
  • Normalise all raw data into a GitHubContext via GitHubNormalizer.
  • Return ConnectorResult.success() when all fetches succeed.
  • Return ConnectorResult.partial() when some PR enrichments fail but others succeed.
  • Return ConnectorResult.failed() when the initial search fails entirely.
  • Implement health_check() via GitHubAPIClient.ping() — never raises.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT read GITHUB_ACCESS_TOKEN — callers construct GitHubAPIClient.
  • It does NOT call IBM Bob.
  • It does NOT know about ContextBuilder or WorkContext.
  • It does NOT import from app.auth.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.base
  • app.connectors.models
  • app.connectors.github.api_client
  • app.connectors.github.normalizer
  • app.connectors.github.models
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
from app.connectors.github.api_client import GitHubAPIClient, GitHubError
from app.connectors.github.normalizer import GitHubNormalizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub search query
# ---------------------------------------------------------------------------

_DEFAULT_SEARCH_QUERY = (
    "is:open is:pr (author:@me OR review-requested:@me OR assignee:@me)"
)


class GitHubConnector(BaseConnector):
    """
    Collects pull request intelligence from GitHub and returns a normalised
    ConnectorResult.

    Parameters
    ----------
    api_client : GitHubAPIClient
        An authenticated GitHub API client carrying a valid access token.

    normalizer : GitHubNormalizer
        The normalizer used to convert raw GitHub dicts into GitHubContext.
        Injected so it can be replaced with a test double.

    max_prs : int
        Maximum number of PRs to enrich per run.  Caps API cost when a user
        has many open PRs.  Defaults to 20.

    Example
    -------
    ::

        client = GitHubAPIClient(access_token="ghp_...")
        connector = GitHubConnector(api_client=client, normalizer=GitHubNormalizer())
        result = await connector.get_context(access_token="ghp_...")
    """

    def __init__(
        self,
        api_client: GitHubAPIClient,
        normalizer: GitHubNormalizer,
        max_prs: int = 20,
    ) -> None:
        self._client = api_client
        self._normalizer = normalizer
        self._max_prs = max_prs

    # ------------------------------------------------------------------
    # BaseConnector — identity
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return "github"

    # ------------------------------------------------------------------
    # BaseConnector — core contract
    # ------------------------------------------------------------------

    async def get_context(self, access_token: str = "") -> ConnectorResult:  # noqa: ARG002
        """
        Discover relevant PRs and enrich each one concurrently with metadata,
        changed files, diff, commits, review comments, reviews, and CI status.

        The access_token argument is accepted for interface compatibility but
        is unused — authentication is via the token baked into GitHubAPIClient
        at construction time.

        Returns
        -------
        ConnectorResult
            ConnectorResult.success()  — all fetches succeeded.
            ConnectorResult.partial()  — search ok, some PR enrichments failed.
            ConnectorResult.failed()   — initial search failed entirely.
        """
        logger.debug("GitHubConnector: starting PR discovery")

        # Step 1 — discover the authenticated user's login (for GitHubContext).
        try:
            user_raw = await self._client.get_authenticated_user()
            authenticated_user: str = user_raw.get("login", "")
        except GitHubError as exc:
            logger.error("GitHubConnector: user fetch failed — %s", exc.message)
            return ConnectorResult.failed(
                source=self.source_name,
                errors=[f"Authenticated user fetch failed: {exc.message}"],
            )

        # Step 2 — search for open PRs involving the authenticated user.
        try:
            raw_search = await self._client.search_pull_requests(_DEFAULT_SEARCH_QUERY)
        except GitHubError as exc:
            logger.error("GitHubConnector: PR search failed — %s", exc.message)
            return ConnectorResult.failed(
                source=self.source_name,
                errors=[f"PR search failed: {exc.message}"],
            )

        items: list[dict[str, Any]] = raw_search.get("items", [])
        # Cap to max_prs to bound API cost.
        items = items[: self._max_prs]

        if not items:
            logger.debug("GitHubConnector: no open PRs found")
            context = self._normalizer.normalize(
                raw_search=raw_search,
                raw_pr_details=[],
                authenticated_user=authenticated_user,
            )
            return ConnectorResult.success(
                source=self.source_name,
                data=context.model_dump(),
                metadata={"prs_enriched": 0, "authenticated_user": authenticated_user},
            )

        # Step 3 — enrich each PR concurrently.
        logger.debug("GitHubConnector: enriching %d PR(s)", len(items))

        enrich_results = await asyncio.gather(
            *[self._enrich_pr(item) for item in items],
            return_exceptions=True,
        )

        # Separate successes from failures.
        enriched: list[dict[str, Any]] = []
        errors: list[str] = []

        for i, result in enumerate(enrich_results):
            if isinstance(result, BaseException):
                pr_number = items[i].get("number", "?")
                repo = _repo_from_search_item(items[i])
                msg = f"Enrichment failed for {repo}#{pr_number}: {result}"
                errors.append(msg)
                logger.warning("GitHubConnector: %s", msg)
            else:
                enriched.append(result)  # type: ignore[arg-type]

        # Step 4 — normalise and build the ConnectorResult.
        context = self._normalizer.normalize(
            raw_search=raw_search,
            raw_pr_details=enriched,
            authenticated_user=authenticated_user,
        )
        data: dict[str, Any] = context.model_dump()
        metadata: dict[str, Any] = {
            "prs_enriched": len(enriched),
            "prs_failed": len(errors),
            "authenticated_user": authenticated_user,
        }

        if errors and not enriched:
            logger.error("GitHubConnector: all PR enrichments failed")
            return ConnectorResult.failed(
                source=self.source_name,
                errors=errors,
                metadata=metadata,
            )

        if errors:
            logger.warning(
                "GitHubConnector: partial result — %d succeeded, %d failed",
                len(enriched), len(errors),
            )
            return ConnectorResult.partial(
                source=self.source_name,
                data=data,
                errors=errors,
                metadata=metadata,
            )

        logger.debug("GitHubConnector: full success — %d PR(s)", len(enriched))
        return ConnectorResult.success(
            source=self.source_name,
            data=data,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # BaseConnector — operational contract
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        Verify that the GitHub API is reachable and the token is valid.

        Delegates to GitHubAPIClient.ping() which returns True/False and
        never raises.

        Returns
        -------
        bool
            True  — GitHub API is reachable and the token is valid.
            False — GitHub API is unreachable or the token is invalid.
        """
        return await self._client.ping()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _enrich_pr(self, search_item: dict[str, Any]) -> dict[str, Any]:
        """
        Fetch all enrichment data for a single PR concurrently.

        Parameters
        ----------
        search_item : dict
            A single item from the search/issues response.  Must contain
            ``number`` and ``repository_url`` (or ``html_url`` as fallback).

        Returns
        -------
        dict
            Enrichment dict with keys: pr, files, diff, commits,
            review_comments, reviews, check_runs.
        """
        number: int = search_item.get("number", 0)
        owner, repo = _parse_owner_repo(search_item)

        # Phase A — fetch the full PR object first so we have head_sha for CI.
        raw_pr = await self._client.get_pull_request(owner, repo, number)
        head_sha: str = raw_pr.get("head", {}).get("sha", "")

        # Phase B — all remaining sub-fetches in parallel.
        (
            raw_files,
            raw_diff,
            raw_commits,
            raw_review_comments,
            raw_reviews,
            raw_check_runs,
        ) = await asyncio.gather(
            self._safe_fetch(
                self._client.get_pull_request_files(owner, repo, number),
                default=[],
                label=f"{owner}/{repo}#{number} files",
            ),
            self._safe_fetch(
                self._client.get_pull_request_diff(owner, repo, number),
                default="",
                label=f"{owner}/{repo}#{number} diff",
            ),
            self._safe_fetch(
                self._client.get_pull_request_commits(owner, repo, number),
                default=[],
                label=f"{owner}/{repo}#{number} commits",
            ),
            self._safe_fetch(
                self._client.get_review_comments(owner, repo, number),
                default=[],
                label=f"{owner}/{repo}#{number} review_comments",
            ),
            self._safe_fetch(
                self._client.get_pull_request_reviews(owner, repo, number),
                default=[],
                label=f"{owner}/{repo}#{number} reviews",
            ),
            self._safe_fetch(
                self._client.get_check_runs(owner, repo, head_sha) if head_sha else None,
                default={},
                label=f"{owner}/{repo}#{number} check_runs",
            ),
        )

        return {
            "pr": raw_pr,
            "files": raw_files,
            "diff": raw_diff,
            "commits": raw_commits,
            "review_comments": raw_review_comments,
            "reviews": raw_reviews,
            "check_runs": raw_check_runs,
        }

    async def _safe_fetch(
        self,
        coro: Any,
        default: Any,
        label: str,
    ) -> Any:
        """
        Await a coroutine and return ``default`` on any exception.

        Individual sub-fetch failures must not abort the entire PR enrichment —
        we return partial data rather than propagating the error.  The
        missing field will be logged as a debug warning but included with
        its default value.

        Parameters
        ----------
        coro : coroutine | None
            The coroutine to await.  When None (e.g., head_sha was empty),
            the default is returned immediately.
        default : Any
            Value to return on failure.
        label : str
            Human-readable label for the log message.
        """
        if coro is None:
            return default
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "GitHubConnector: sub-fetch failed for %s — %s: %s",
                label, type(exc).__name__, exc,
            )
            return default


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _parse_owner_repo(search_item: dict[str, Any]) -> tuple[str, str]:
    """
    Extract the ``owner`` and ``repo`` strings from a search result item.

    GitHub's search/issues response includes a ``repository_url`` field:
        ``https://api.github.com/repos/acme/my-repo``

    Falls back to parsing ``html_url`` when ``repository_url`` is absent.

    Returns
    -------
    tuple[str, str]
        (owner, repo) — both empty strings when parsing fails.
    """
    repo_url: str = search_item.get("repository_url", "")
    if repo_url:
        # https://api.github.com/repos/owner/repo → owner, repo
        parts = repo_url.rstrip("/").rsplit("/", 2)
        if len(parts) >= 2:
            return parts[-2], parts[-1]

    # Fallback — parse html_url: https://github.com/owner/repo/pull/42
    html_url: str = search_item.get("html_url", "")
    if "/pull/" in html_url:
        base = html_url.split("/pull/")[0]
        parts = base.rstrip("/").rsplit("/", 2)
        if len(parts) >= 2:
            return parts[-2], parts[-1]

    return "", ""


def _repo_from_search_item(search_item: dict[str, Any]) -> str:
    """Return ``owner/repo`` from a search result item for log messages."""
    owner, repo = _parse_owner_repo(search_item)
    return f"{owner}/{repo}" if owner else "unknown/unknown"
