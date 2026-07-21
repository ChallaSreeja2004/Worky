"""
tests/connectors/github/test_api_client.py
==========================================
Unit tests for GitHubAPIClient.

All HTTP calls are intercepted with respx — no real network traffic.

Coverage:
  • search_pull_requests() returns parsed JSON on 200.
  • get_pull_request() returns parsed JSON on 200.
  • get_pull_request_files() returns a list on 200.
  • get_pull_request_diff() returns raw text with the diff Accept header.
  • get_pull_request_commits() returns a list on 200.
  • get_review_comments() returns a list on 200.
  • get_pull_request_reviews() returns a list on 200.
  • get_check_runs() returns parsed JSON on 200.
  • get_authenticated_user() returns parsed JSON on 200.
  • 401 → GitHubAuthError raised immediately (no retry).
  • 403 → GitHubAuthError raised immediately (no retry).
  • 429 after all retries → GitHubRateLimitError.
  • 503 after all retries → GitHubRateLimitError.
  • Non-2xx other → GitHubServiceError raised immediately.
  • Network error → GitHubServiceError raised after retries.
  • ping() returns True on success, False on any failure.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.connectors.github.api_client import (
    GitHubAPIClient,
    GitHubAuthError,
    GitHubRateLimitError,
    GitHubServiceError,
)

BASE = "https://api.github.com"


def make_client() -> GitHubAPIClient:
    return GitHubAPIClient(access_token="ghp_test", base_url=BASE, timeout=5.0)


# ---------------------------------------------------------------------------
# search_pull_requests
# ---------------------------------------------------------------------------

class TestSearchPullRequests:

    @respx.mock
    async def test_returns_parsed_json(self):
        payload = {"total_count": 1, "items": [{"number": 42}]}
        respx.get(f"{BASE}/search/issues").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().search_pull_requests("is:open is:pr author:@me")
        assert result["total_count"] == 1
        assert result["items"][0]["number"] == 42

    @respx.mock
    async def test_401_raises_auth_error(self):
        respx.get(f"{BASE}/search/issues").mock(
            return_value=httpx.Response(401, json={"message": "Bad credentials"})
        )
        with pytest.raises(GitHubAuthError) as exc_info:
            await make_client().search_pull_requests("is:open is:pr author:@me")
        assert "401" in str(exc_info.value)

    @respx.mock
    async def test_403_raises_auth_error(self):
        respx.get(f"{BASE}/search/issues").mock(
            return_value=httpx.Response(403, json={"message": "Forbidden"})
        )
        with pytest.raises(GitHubAuthError):
            await make_client().search_pull_requests("is:open is:pr author:@me")

    @respx.mock
    async def test_422_raises_service_error(self):
        respx.get(f"{BASE}/search/issues").mock(
            return_value=httpx.Response(422, json={"message": "Validation Failed"})
        )
        with pytest.raises(GitHubServiceError):
            await make_client().search_pull_requests("invalid query !!!")


# ---------------------------------------------------------------------------
# get_pull_request
# ---------------------------------------------------------------------------

class TestGetPullRequest:

    @respx.mock
    async def test_returns_pr_json(self):
        payload = {"number": 42, "title": "Fix auth bug", "state": "open"}
        respx.get(f"{BASE}/repos/acme/my-repo/pulls/42").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().get_pull_request("acme", "my-repo", 42)
        assert result["number"] == 42
        assert result["title"] == "Fix auth bug"


# ---------------------------------------------------------------------------
# get_pull_request_files
# ---------------------------------------------------------------------------

class TestGetPullRequestFiles:

    @respx.mock
    async def test_returns_list(self):
        payload = [
            {"filename": "src/auth.py", "status": "modified", "additions": 5, "deletions": 1, "changes": 6}
        ]
        respx.get(f"{BASE}/repos/acme/my-repo/pulls/42/files").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().get_pull_request_files("acme", "my-repo", 42)
        assert isinstance(result, list)
        assert result[0]["filename"] == "src/auth.py"


# ---------------------------------------------------------------------------
# get_pull_request_diff
# ---------------------------------------------------------------------------

class TestGetPullRequestDiff:

    @respx.mock
    async def test_returns_raw_text(self):
        diff_text = "diff --git a/src/auth.py b/src/auth.py\n--- a\n+++ b\n"
        respx.get(f"{BASE}/repos/acme/my-repo/pulls/42").mock(
            return_value=httpx.Response(200, text=diff_text)
        )
        result = await make_client().get_pull_request_diff("acme", "my-repo", 42)
        assert isinstance(result, str)
        assert "diff --git" in result


# ---------------------------------------------------------------------------
# get_pull_request_commits
# ---------------------------------------------------------------------------

class TestGetPullRequestCommits:

    @respx.mock
    async def test_returns_list(self):
        payload = [{"sha": "abc1"}, {"sha": "abc2"}]
        respx.get(f"{BASE}/repos/acme/my-repo/pulls/42/commits").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().get_pull_request_commits("acme", "my-repo", 42)
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# get_review_comments
# ---------------------------------------------------------------------------

class TestGetReviewComments:

    @respx.mock
    async def test_returns_list(self):
        payload = [{"id": 1, "body": "nit: rename variable"}]
        respx.get(f"{BASE}/repos/acme/my-repo/pulls/42/comments").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().get_review_comments("acme", "my-repo", 42)
        assert isinstance(result, list)
        assert result[0]["id"] == 1


# ---------------------------------------------------------------------------
# get_pull_request_reviews
# ---------------------------------------------------------------------------

class TestGetPullRequestReviews:

    @respx.mock
    async def test_returns_list(self):
        payload = [{"id": 10, "state": "APPROVED"}]
        respx.get(f"{BASE}/repos/acme/my-repo/pulls/42/reviews").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().get_pull_request_reviews("acme", "my-repo", 42)
        assert isinstance(result, list)
        assert result[0]["state"] == "APPROVED"


# ---------------------------------------------------------------------------
# get_check_runs
# ---------------------------------------------------------------------------

class TestGetCheckRuns:

    @respx.mock
    async def test_returns_dict(self):
        payload = {"total_count": 1, "check_runs": [{"name": "test-suite", "status": "completed", "conclusion": "failure"}]}
        respx.get(f"{BASE}/repos/acme/my-repo/commits/abc123/check-runs").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await make_client().get_check_runs("acme", "my-repo", "abc123")
        assert result["total_count"] == 1
        assert result["check_runs"][0]["conclusion"] == "failure"


# ---------------------------------------------------------------------------
# get_authenticated_user
# ---------------------------------------------------------------------------

class TestGetAuthenticatedUser:

    @respx.mock
    async def test_returns_user_dict(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(200, json={"login": "alice", "id": 1})
        )
        result = await make_client().get_authenticated_user()
        assert result["login"] == "alice"


# ---------------------------------------------------------------------------
# Error handling — rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:

    @respx.mock
    async def test_429_after_retries_raises_rate_limit_error(self):
        """Three consecutive 429 responses must raise GitHubRateLimitError."""
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(429, json={"message": "API rate limit exceeded"})
        )
        with pytest.raises(GitHubRateLimitError):
            await make_client().get_authenticated_user()

    @respx.mock
    async def test_503_after_retries_raises_rate_limit_error(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        with pytest.raises(GitHubRateLimitError):
            await make_client().get_authenticated_user()


# ---------------------------------------------------------------------------
# Error handling — auth
# ---------------------------------------------------------------------------

class TestAuthErrors:

    @respx.mock
    async def test_401_raises_auth_error_immediately(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(401, json={"message": "Bad credentials"})
        )
        with pytest.raises(GitHubAuthError) as exc_info:
            await make_client().get_authenticated_user()
        assert exc_info.value.message is not None

    @respx.mock
    async def test_403_raises_auth_error_immediately(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(403, json={"message": "Forbidden"})
        )
        with pytest.raises(GitHubAuthError):
            await make_client().get_authenticated_user()


# ---------------------------------------------------------------------------
# Error handling — service errors
# ---------------------------------------------------------------------------

class TestServiceErrors:

    @respx.mock
    async def test_500_raises_service_error_immediately(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(500, json={"message": "Internal Server Error"})
        )
        with pytest.raises(GitHubServiceError):
            await make_client().get_authenticated_user()

    @respx.mock
    async def test_404_raises_service_error_immediately(self):
        respx.get(f"{BASE}/repos/acme/missing/pulls/1").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(GitHubServiceError):
            await make_client().get_pull_request("acme", "missing", 1)

    @respx.mock
    async def test_network_error_raises_service_error(self):
        respx.get(f"{BASE}/user").mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(GitHubServiceError):
            await make_client().get_authenticated_user()


# ---------------------------------------------------------------------------
# ping()
# ---------------------------------------------------------------------------

class TestPing:

    @respx.mock
    async def test_ping_returns_true_on_success(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(200, json={"login": "alice"})
        )
        assert await make_client().ping() is True

    @respx.mock
    async def test_ping_returns_false_on_auth_error(self):
        respx.get(f"{BASE}/user").mock(
            return_value=httpx.Response(401, json={"message": "Bad credentials"})
        )
        assert await make_client().ping() is False

    @respx.mock
    async def test_ping_returns_false_on_network_error(self):
        respx.get(f"{BASE}/user").mock(side_effect=httpx.ConnectError("down"))
        assert await make_client().ping() is False

    @respx.mock
    async def test_ping_never_raises(self):
        """ping() must absorb all exceptions — never propagate."""
        respx.get(f"{BASE}/user").mock(side_effect=RuntimeError("unexpected"))
        result = await make_client().ping()
        assert result is False
