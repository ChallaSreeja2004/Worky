"""
app/connectors/github/normalizer.py
=====================================
GitHubNormalizer — transforms raw GitHub REST API JSON into Worky domain models.

RESPONSIBILITIES
----------------
  • Accept raw API response dicts/lists from GitHubAPIClient.
  • Map each raw dict to the appropriate Worky domain model.
  • Return a fully populated GitHubContext.
  • Handle every optional field defensively using .get() — never assume a key exists.
  • Truncate the PR diff to DIFF_TRUNCATE_CHARS characters to keep
    the IBM Bob prompt within token limits.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT make any API calls.
  • It does NOT call GitHubAPIClient.
  • It does NOT contain business logic (prioritisation, scoring, filtering).

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.github.models
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.connectors.github.models import (
    CICheckRun,
    GitHubContext,
    PRFile,
    PRReview,
    PullRequest,
    ReviewComment,
)

logger = logging.getLogger(__name__)

# Maximum characters kept from the unified diff.
# Keeps the ConnectorResult serialisable and the Bob prompt within token limits.
DIFF_TRUNCATE_CHARS: int = 2000


def _parse_dt(value: str | None) -> datetime:
    """
    Parse an ISO-8601 datetime string from the GitHub API into a UTC datetime.

    GitHub returns timestamps in the form ``2024-01-15T10:30:00Z``.
    Falls back to the current UTC time when the value is absent or unparseable,
    ensuring models are always fully populated.
    """
    if not value:
        return datetime.now(timezone.utc)
    try:
        # Python 3.11+ handles trailing 'Z' natively via fromisoformat.
        # For 3.9/3.10 compatibility we replace it with '+00:00'.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning("GitHubNormalizer: could not parse datetime %r — using now()", value)
        return datetime.now(timezone.utc)


def _repo_from_url(html_url: str) -> str:
    """
    Derive ``owner/repo`` from a GitHub HTML URL.

    Example:
        ``https://github.com/acme/my-repo/pull/42`` → ``"acme/my-repo"``

    Returns an empty string when the URL cannot be parsed.
    """
    try:
        # Strip trailing slashes and split on '/pull/' to isolate the repo path.
        base = html_url.split("/pull/")[0]          # https://github.com/acme/my-repo
        parts = base.rstrip("/").rsplit("/", 2)     # ['https://github.com', 'acme', 'my-repo']
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
    except Exception:  # noqa: BLE001
        pass
    return ""


class GitHubNormalizer:
    """
    Pure transformation layer between raw GitHub REST API JSON and Worky models.

    All methods are stateless — the class exists only to group related
    normalisation logic.  No instance state is held.

    Usage
    -----
    ::

        normalizer = GitHubNormalizer()
        context = normalizer.normalize(
            raw_search=search_result,
            raw_pr_details=list_of_enriched_dicts,
            authenticated_user="alice",
        )
        # context → GitHubContext
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def normalize(
        self,
        raw_search: dict[str, Any],
        raw_pr_details: list[dict[str, Any]],
        authenticated_user: str,
    ) -> GitHubContext:
        """
        Build a GitHubContext from the raw GitHub API payloads.

        Parameters
        ----------
        raw_search : dict
            Raw response from ``GitHubAPIClient.search_pull_requests()``.
            Contains ``total_count`` and ``items``.
        raw_pr_details : list[dict]
            List of per-PR enrichment dicts produced by GitHubConnector for
            each PR found in the search.  Each dict has the keys:
              ``pr``              — raw PR object from get_pull_request()
              ``files``           — raw file list from get_pull_request_files()
              ``diff``            — raw diff string from get_pull_request_diff()
              ``commits``         — raw commit list from get_pull_request_commits()
              ``review_comments`` — raw comment list from get_review_comments()
              ``reviews``         — raw review list from get_pull_request_reviews()
              ``check_runs``      — raw check-runs dict from get_check_runs()
        authenticated_user : str
            GitHub login of the authenticated user.

        Returns
        -------
        GitHubContext
            Fully populated normalised context.
        """
        total_count: int = raw_search.get("total_count", 0)
        pull_requests = [self._normalize_pr(d) for d in raw_pr_details]

        logger.debug(
            "GitHubNormalizer: normalised %d PR(s) (total found: %d)",
            len(pull_requests), total_count,
        )

        return GitHubContext(
            pull_requests=pull_requests,
            total_prs_found=total_count,
            authenticated_user=authenticated_user,
        )

    # ------------------------------------------------------------------
    # Internal normalisation helpers
    # ------------------------------------------------------------------

    def _normalize_pr(self, enrichment: dict[str, Any]) -> PullRequest:
        """
        Build a fully enriched PullRequest model from one enrichment dict.

        Each enrichment dict was assembled by GitHubConnector from the results
        of up to seven concurrent API sub-fetches.  Missing keys mean the
        sub-fetch failed; the normalizer returns empty/default values in that
        case so the PullRequest is still included in the output.
        """
        raw: dict[str, Any] = enrichment.get("pr", {})

        # Repository can be derived from the PR's HTML URL.
        html_url: str = raw.get("html_url", "")
        repository = _repo_from_url(html_url)

        # Labels: GitHub returns [{"id": ..., "name": "...", ...}, ...]
        labels: list[str] = [
            lbl.get("name", "")
            for lbl in raw.get("labels", [])
            if lbl.get("name")
        ]

        # Head commit SHA — needed for CI check lookup by the connector.
        head: dict[str, Any] = raw.get("head", {})
        base: dict[str, Any] = raw.get("base", {})

        pr = PullRequest(
            number=raw.get("number", 0),
            title=raw.get("title", ""),
            body=raw.get("body") or "",
            author=raw.get("user", {}).get("login", ""),
            state=raw.get("state", "open"),
            html_url=html_url,
            base_branch=base.get("ref", ""),
            head_branch=head.get("ref", ""),
            head_sha=head.get("sha", ""),
            created_at=_parse_dt(raw.get("created_at")),
            updated_at=_parse_dt(raw.get("updated_at")),
            labels=labels,
            mergeable=raw.get("mergeable"),
            draft=raw.get("draft", False),
            repository=repository,
            files=self._normalize_files(enrichment.get("files", [])),
            commits_count=len(enrichment.get("commits", [])),
            review_comments=self._normalize_review_comments(
                enrichment.get("review_comments", [])
            ),
            reviews=self._normalize_reviews(enrichment.get("reviews", [])),
            ci_checks=self._normalize_check_runs(
                enrichment.get("check_runs", {})
            ),
            diff_summary=self._truncate_diff(enrichment.get("diff", "")),
        )

        return pr

    def _normalize_files(self, raw_files: list[dict[str, Any]]) -> list[PRFile]:
        """Map raw file objects to PRFile models."""
        result = []
        for f in raw_files:
            result.append(
                PRFile(
                    filename=f.get("filename", ""),
                    status=f.get("status", "modified"),
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    changes=f.get("changes", 0),
                )
            )
        return result

    def _normalize_review_comments(
        self, raw_comments: list[dict[str, Any]]
    ) -> list[ReviewComment]:
        """Map raw inline review comment objects to ReviewComment models."""
        result = []
        for c in raw_comments:
            result.append(
                ReviewComment(
                    id=c.get("id", 0),
                    author=c.get("user", {}).get("login", ""),
                    body=c.get("body") or "",
                    path=c.get("path", ""),
                    created_at=_parse_dt(c.get("created_at")),
                    updated_at=_parse_dt(c.get("updated_at")),
                )
            )
        return result

    def _normalize_reviews(
        self, raw_reviews: list[dict[str, Any]]
    ) -> list[PRReview]:
        """Map raw PR review objects to PRReview models."""
        result = []
        for r in raw_reviews:
            submitted_raw = r.get("submitted_at")
            submitted_at = _parse_dt(submitted_raw) if submitted_raw else None
            result.append(
                PRReview(
                    id=r.get("id", 0),
                    author=r.get("user", {}).get("login", ""),
                    state=r.get("state", "PENDING"),
                    submitted_at=submitted_at,
                    body=r.get("body") or "",
                )
            )
        return result

    def _normalize_check_runs(
        self, raw_check_runs: dict[str, Any]
    ) -> list[CICheckRun]:
        """Map the raw check-runs API response to a list of CICheckRun models."""
        runs: list[dict[str, Any]] = raw_check_runs.get("check_runs", [])
        result = []
        for run in runs:
            started_raw = run.get("started_at")
            completed_raw = run.get("completed_at")
            result.append(
                CICheckRun(
                    name=run.get("name", ""),
                    status=run.get("status", "queued"),
                    conclusion=run.get("conclusion"),
                    started_at=_parse_dt(started_raw) if started_raw else None,
                    completed_at=_parse_dt(completed_raw) if completed_raw else None,
                )
            )
        return result

    def _truncate_diff(self, diff: str) -> str:
        """Truncate the raw diff to DIFF_TRUNCATE_CHARS characters."""
        if not diff:
            return ""
        if len(diff) <= DIFF_TRUNCATE_CHARS:
            return diff
        return diff[:DIFF_TRUNCATE_CHARS] + "\n... [diff truncated]"
