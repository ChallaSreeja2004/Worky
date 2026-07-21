"""
tests/connectors/github/test_connector.py
==========================================
Unit tests for GitHubConnector.

GitHubAPIClient is replaced with AsyncMock on every test — no real HTTP calls.

Coverage:
  • Successful run returns ConnectorResult.success with populated data.
  • No PRs found → ConnectorResult.success with empty pull_requests list.
  • All three search queries fail → ConnectorResult.success with empty list
    (search errors are non-fatal; the connector cannot distinguish "no results"
    from "all queries failed gracefully").
  • User fetch fails → ConnectorResult.failed.
  • Duplicate PRs across search queries are deduplicated.
  • Some PR enrichments fail → ConnectorResult.partial.
  • All PR enrichments fail → ConnectorResult.failed.
  • max_prs cap is respected.
  • health_check() delegates to api_client.ping().
  • source_name is "github".
  • Three search queries are issued (one per qualifier).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, call

import pytest

from app.connectors.github.api_client import GitHubAuthError, GitHubServiceError
from app.connectors.github.connector import GitHubConnector, _SEARCH_QUERIES
from app.connectors.github.normalizer import GitHubNormalizer
from app.connectors.models import ConnectorStatus

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RAW_USER = {"login": "alice", "id": 1}

# One PR returned by the first search query; other two queries return empty.
RAW_SEARCH_ONE_PR: dict[str, Any] = {
    "total_count": 1,
    "items": [
        {
            "number": 42,
            "html_url": "https://github.com/acme/my-repo/pull/42",
            "repository_url": "https://api.github.com/repos/acme/my-repo",
        }
    ],
}

RAW_SEARCH_EMPTY: dict[str, Any] = {"total_count": 0, "items": []}

RAW_PR: dict[str, Any] = {
    "number": 42,
    "title": "Fix auth bug",
    "body": "Fixes the login issue.",
    "state": "open",
    "html_url": "https://github.com/acme/my-repo/pull/42",
    "draft": False,
    "mergeable": True,
    "user": {"login": "alice"},
    "head": {"ref": "feature/fix-auth", "sha": "abc123"},
    "base": {"ref": "main"},
    "labels": [],
    "created_at": "2024-06-10T09:00:00Z",
    "updated_at": "2024-06-10T11:00:00Z",
}


def make_happy_client() -> AsyncMock:
    """
    Return a mock client where all calls succeed.

    search_pull_requests is configured as a side_effect so that:
      • query "is:open is:pr author:@me"           → one PR
      • query "is:open is:pr review-requested:@me" → empty
      • query "is:open is:pr assignee:@me"         → empty
    This mirrors the real behaviour (one query matches, others don't).
    """
    def _search_side_effect(query: str) -> dict[str, Any]:
        if "author:@me" in query:
            return RAW_SEARCH_ONE_PR
        return RAW_SEARCH_EMPTY

    client = AsyncMock()
    client.get_authenticated_user = AsyncMock(return_value=RAW_USER)
    client.search_pull_requests = AsyncMock(side_effect=_search_side_effect)
    client.get_pull_request = AsyncMock(return_value=RAW_PR)
    client.get_pull_request_files = AsyncMock(return_value=[])
    client.get_pull_request_diff = AsyncMock(return_value="")
    client.get_pull_request_commits = AsyncMock(return_value=[])
    client.get_review_comments = AsyncMock(return_value=[])
    client.get_pull_request_reviews = AsyncMock(return_value=[])
    client.get_check_runs = AsyncMock(return_value={"total_count": 0, "check_runs": []})
    client.ping = AsyncMock(return_value=True)
    return client


def make_connector(client: AsyncMock, max_prs: int = 20) -> GitHubConnector:
    return GitHubConnector(
        api_client=client,
        normalizer=GitHubNormalizer(),
        max_prs=max_prs,
    )


# ---------------------------------------------------------------------------
# source_name
# ---------------------------------------------------------------------------

class TestSourceName:

    def test_source_name_is_github(self):
        connector = make_connector(make_happy_client())
        assert connector.source_name == "github"


# ---------------------------------------------------------------------------
# Successful run
# ---------------------------------------------------------------------------

class TestGetContextSuccess:

    async def test_returns_success_status(self):
        result = await make_connector(make_happy_client()).get_context()
        assert result.status == ConnectorStatus.SUCCESS

    async def test_source_field_is_github(self):
        result = await make_connector(make_happy_client()).get_context()
        assert result.source == "github"

    async def test_pull_requests_in_data(self):
        result = await make_connector(make_happy_client()).get_context()
        assert "pull_requests" in result.data
        assert len(result.data["pull_requests"]) == 1

    async def test_authenticated_user_in_data(self):
        result = await make_connector(make_happy_client()).get_context()
        assert result.data["authenticated_user"] == "alice"

    async def test_no_errors_on_success(self):
        result = await make_connector(make_happy_client()).get_context()
        assert result.errors == []

    async def test_metadata_contains_prs_enriched(self):
        result = await make_connector(make_happy_client()).get_context()
        assert result.metadata.get("prs_enriched") == 1

    async def test_three_search_queries_are_issued(self):
        """Connector must run exactly three targeted queries, not one grouped query."""
        client = make_happy_client()
        await make_connector(client).get_context()
        assert client.search_pull_requests.await_count == 3

    async def test_all_three_query_strings_contain_is_open_is_pr(self):
        client = make_happy_client()
        await make_connector(client).get_context()
        for c in client.search_pull_requests.call_args_list:
            query = c[0][0]
            assert "is:open" in query
            assert "is:pr" in query

    async def test_no_parenthesised_or_in_queries(self):
        """The 422-causing grouped OR syntax must not appear in any query."""
        client = make_happy_client()
        await make_connector(client).get_context()
        for c in client.search_pull_requests.call_args_list:
            query = c[0][0]
            assert "(" not in query
            assert " OR " not in query

    async def test_all_sub_fetches_called(self):
        client = make_happy_client()
        await make_connector(client).get_context()
        client.get_pull_request.assert_awaited_once_with("acme", "my-repo", 42)
        client.get_pull_request_files.assert_awaited_once()
        client.get_pull_request_diff.assert_awaited_once()
        client.get_pull_request_commits.assert_awaited_once()
        client.get_review_comments.assert_awaited_once()
        client.get_pull_request_reviews.assert_awaited_once()
        client.get_check_runs.assert_awaited_once()


# ---------------------------------------------------------------------------
# Deduplication — same PR appears in multiple query results
# ---------------------------------------------------------------------------

class TestDeduplication:

    async def test_same_pr_in_multiple_queries_is_enriched_once(self):
        """PR #42 returned by both author and review-requested queries → enriched once."""
        pr_item = {
            "number": 42,
            "html_url": "https://github.com/acme/my-repo/pull/42",
            "repository_url": "https://api.github.com/repos/acme/my-repo",
        }

        client = make_happy_client()
        # All three queries return the same PR.
        client.search_pull_requests = AsyncMock(
            return_value={"total_count": 1, "items": [pr_item]}
        )

        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.SUCCESS
        assert len(result.data["pull_requests"]) == 1
        # get_pull_request should only be called once despite three search hits.
        client.get_pull_request.assert_awaited_once()


# ---------------------------------------------------------------------------
# Empty PR list
# ---------------------------------------------------------------------------

class TestGetContextNoPRs:

    async def test_empty_search_returns_success(self):
        client = make_happy_client()
        client.search_pull_requests = AsyncMock(return_value=RAW_SEARCH_EMPTY)
        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.SUCCESS
        assert result.data["pull_requests"] == []
        assert result.data["total_prs_found"] == 0

    async def test_no_sub_fetches_called_when_no_prs(self):
        client = make_happy_client()
        client.search_pull_requests = AsyncMock(return_value=RAW_SEARCH_EMPTY)
        await make_connector(client).get_context()
        client.get_pull_request.assert_not_awaited()


# ---------------------------------------------------------------------------
# User fetch failure
# ---------------------------------------------------------------------------

class TestGetContextUserFetchFails:

    async def test_user_fetch_failure_returns_failed(self):
        client = make_happy_client()
        client.get_authenticated_user = AsyncMock(
            side_effect=GitHubAuthError("Bad credentials")
        )
        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.FAILED

    async def test_user_fetch_failure_error_message_present(self):
        client = make_happy_client()
        client.get_authenticated_user = AsyncMock(
            side_effect=GitHubAuthError("Bad credentials")
        )
        result = await make_connector(client).get_context()
        assert any("user" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Search failure
# ---------------------------------------------------------------------------

class TestGetContextSearchFails:

    async def test_all_searches_fail_returns_success_with_empty_list(self):
        """
        All three search queries failing (gracefully returning None via _safe_search)
        is treated as zero PRs found — not a hard FAILED result.  The connector
        cannot distinguish "API returned empty" from "API failed silently".
        """
        client = make_happy_client()
        client.search_pull_requests = AsyncMock(
            side_effect=GitHubServiceError("search endpoint unreachable")
        )
        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.SUCCESS
        assert result.data["pull_requests"] == []

    async def test_partial_search_failure_still_processes_successful_queries(self):
        """
        If one of three queries fails, the PRs from the other two are still
        returned in the result.
        """
        pr_item = {
            "number": 42,
            "html_url": "https://github.com/acme/my-repo/pull/42",
            "repository_url": "https://api.github.com/repos/acme/my-repo",
        }

        def _search_side_effect(query: str) -> dict[str, Any]:
            if "author:@me" in query:
                raise GitHubServiceError("422 Validation Failed")
            if "review-requested:@me" in query:
                return {"total_count": 1, "items": [pr_item]}
            return RAW_SEARCH_EMPTY

        client = make_happy_client()
        client.search_pull_requests = AsyncMock(side_effect=_search_side_effect)

        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.SUCCESS
        assert len(result.data["pull_requests"]) == 1


# ---------------------------------------------------------------------------
# Partial enrichment failure
# ---------------------------------------------------------------------------

class TestGetContextPartialEnrichment:

    async def test_single_pr_enrichment_failure_returns_partial(self):
        """When one PR's get_pull_request fails, that PR is dropped but the
        overall result is PARTIAL (remaining PRs still succeeded)."""
        two_pr_items = [
            {
                "number": 1,
                "html_url": "https://github.com/acme/repo/pull/1",
                "repository_url": "https://api.github.com/repos/acme/repo",
            },
            {
                "number": 2,
                "html_url": "https://github.com/acme/repo/pull/2",
                "repository_url": "https://api.github.com/repos/acme/repo",
            },
        ]
        raw_pr_2 = {**RAW_PR, "number": 2}

        async def get_pr_side_effect(owner, repo, number):
            if number == 1:
                raise GitHubServiceError("PR 1 fetch failed")
            return raw_pr_2

        client = make_happy_client()
        # First query returns both PRs; other two return empty.
        client.search_pull_requests = AsyncMock(
            side_effect=lambda q: (
                {"total_count": 2, "items": two_pr_items}
                if "author:@me" in q else RAW_SEARCH_EMPTY
            )
        )
        client.get_pull_request = AsyncMock(side_effect=get_pr_side_effect)

        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.PARTIAL
        assert len(result.errors) == 1
        assert len(result.data["pull_requests"]) == 1

    async def test_all_pr_enrichments_fail_returns_failed(self):
        client = make_happy_client()
        client.get_pull_request = AsyncMock(
            side_effect=GitHubServiceError("PR fetch unavailable")
        )
        result = await make_connector(client).get_context()
        assert result.status == ConnectorStatus.FAILED


# ---------------------------------------------------------------------------
# max_prs cap
# ---------------------------------------------------------------------------

class TestMaxPRsCap:

    async def test_max_prs_caps_enrichment(self):
        """When search returns more PRs than max_prs, only max_prs are enriched."""
        many_items = [
            {
                "number": i,
                "html_url": f"https://github.com/acme/repo/pull/{i}",
                "repository_url": "https://api.github.com/repos/acme/repo",
            }
            for i in range(1, 11)  # 10 PRs
        ]
        search_result = {"total_count": 10, "items": many_items}

        client = make_happy_client()
        client.search_pull_requests = AsyncMock(return_value=search_result)
        # get_pull_request returns a valid PR for any number
        client.get_pull_request = AsyncMock(
            side_effect=lambda owner, repo, number: {**RAW_PR, "number": number}
        )

        result = await make_connector(client, max_prs=3).get_context()
        assert result.status == ConnectorStatus.SUCCESS
        # Only 3 PRs enriched despite 10 found across all queries (deduplicated).
        assert result.metadata.get("prs_enriched") == 3


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:

    async def test_health_check_true_when_ping_succeeds(self):
        client = make_happy_client()
        client.ping = AsyncMock(return_value=True)
        assert await make_connector(client).health_check() is True

    async def test_health_check_false_when_ping_fails(self):
        client = make_happy_client()
        client.ping = AsyncMock(return_value=False)
        assert await make_connector(client).health_check() is False
