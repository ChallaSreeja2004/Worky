"""
tests/connectors/github/test_normalizer.py
==========================================
Unit tests for GitHubNormalizer.

No HTTP calls — pure transformation.

Coverage:
  • normalize() builds a GitHubContext from raw API payloads.
  • _normalize_pr() maps all PR fields correctly.
  • _normalize_files() maps PRFile fields.
  • _normalize_review_comments() maps ReviewComment fields.
  • _normalize_reviews() maps PRReview fields; pending review has no submitted_at.
  • _normalize_check_runs() maps CICheckRun fields.
  • _truncate_diff() truncates diffs longer than DIFF_TRUNCATE_CHARS.
  • Labels are extracted from nested dicts correctly.
  • repository is derived from html_url.
  • Missing/None fields use safe defaults (never raise KeyError).
"""

from __future__ import annotations

from typing import Any

from app.connectors.github.normalizer import GitHubNormalizer, DIFF_TRUNCATE_CHARS, _repo_from_url

# ---------------------------------------------------------------------------
# Shared raw data fixtures
# ---------------------------------------------------------------------------

RAW_PR: dict[str, Any] = {
    "number": 42,
    "title": "Fix auth bug",
    "body": "Fixes the login issue.",
    "state": "open",
    "html_url": "https://github.com/acme/my-repo/pull/42",
    "draft": False,
    "mergeable": True,
    "user": {"login": "alice"},
    "head": {"ref": "feature/fix-auth", "sha": "abc123def456"},
    "base": {"ref": "main"},
    "labels": [{"id": 1, "name": "bug"}, {"id": 2, "name": "priority:high"}],
    "created_at": "2024-06-10T09:00:00Z",
    "updated_at": "2024-06-10T11:00:00Z",
}

RAW_FILES: list[dict[str, Any]] = [
    {"filename": "src/auth.py", "status": "modified", "additions": 10, "deletions": 3, "changes": 13},
    {"filename": "tests/test_auth.py", "status": "added", "additions": 25, "deletions": 0, "changes": 25},
]

RAW_COMMITS: list[dict[str, Any]] = [
    {"sha": "abc1", "commit": {"message": "Fix token refresh"}},
    {"sha": "abc2", "commit": {"message": "Add tests"}},
]

RAW_REVIEW_COMMENTS: list[dict[str, Any]] = [
    {
        "id": 101,
        "user": {"login": "bob"},
        "body": "Please add a docstring.",
        "path": "src/auth.py",
        "created_at": "2024-06-10T10:00:00Z",
        "updated_at": "2024-06-10T10:05:00Z",
    }
]

RAW_REVIEWS: list[dict[str, Any]] = [
    {
        "id": 201,
        "user": {"login": "carol"},
        "state": "APPROVED",
        "submitted_at": "2024-06-10T10:30:00Z",
        "body": "LGTM",
    },
    {
        "id": 202,
        "user": {"login": "dave"},
        "state": "CHANGES_REQUESTED",
        "submitted_at": "2024-06-10T10:45:00Z",
        "body": "Please fix the nit.",
    },
]

RAW_CHECK_RUNS: dict[str, Any] = {
    "total_count": 2,
    "check_runs": [
        {
            "name": "test-suite",
            "status": "completed",
            "conclusion": "failure",
            "started_at": "2024-06-10T10:00:00Z",
            "completed_at": "2024-06-10T10:10:00Z",
        },
        {
            "name": "lint",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2024-06-10T10:00:00Z",
            "completed_at": "2024-06-10T10:02:00Z",
        },
    ],
}

RAW_SEARCH: dict[str, Any] = {"total_count": 3, "items": []}

ENRICHMENT: dict[str, Any] = {
    "pr": RAW_PR,
    "files": RAW_FILES,
    "diff": "diff --git a/src/auth.py b/src/auth.py\n--- a/src/auth.py\n+++ b/src/auth.py\n",
    "commits": RAW_COMMITS,
    "review_comments": RAW_REVIEW_COMMENTS,
    "reviews": RAW_REVIEWS,
    "check_runs": RAW_CHECK_RUNS,
}


def make_normalizer() -> GitHubNormalizer:
    return GitHubNormalizer()


# ---------------------------------------------------------------------------
# _repo_from_url helper
# ---------------------------------------------------------------------------

class TestRepoFromUrl:

    def test_extracts_owner_repo(self):
        url = "https://github.com/acme/my-repo/pull/42"
        assert _repo_from_url(url) == "acme/my-repo"

    def test_empty_url_returns_empty_string(self):
        assert _repo_from_url("") == ""

    def test_malformed_url_returns_empty_string(self):
        assert _repo_from_url("not-a-url") == ""


# ---------------------------------------------------------------------------
# normalize() top-level
# ---------------------------------------------------------------------------

class TestNormalize:

    def test_returns_github_context(self):
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[ENRICHMENT],
            authenticated_user="alice",
        )
        assert ctx.authenticated_user == "alice"
        assert ctx.total_prs_found == 3
        assert len(ctx.pull_requests) == 1

    def test_empty_pr_list(self):
        ctx = make_normalizer().normalize(
            raw_search={"total_count": 0},
            raw_pr_details=[],
            authenticated_user="alice",
        )
        assert ctx.pull_requests == []
        assert ctx.total_prs_found == 0

    def test_missing_total_count_defaults_to_zero(self):
        ctx = make_normalizer().normalize(
            raw_search={},
            raw_pr_details=[],
            authenticated_user="alice",
        )
        assert ctx.total_prs_found == 0


# ---------------------------------------------------------------------------
# PR field mapping
# ---------------------------------------------------------------------------

class TestNormalizePR:

    def setup_method(self):
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[ENRICHMENT],
            authenticated_user="alice",
        )
        self.pr = ctx.pull_requests[0]

    def test_number(self):
        assert self.pr.number == 42

    def test_title(self):
        assert self.pr.title == "Fix auth bug"

    def test_author(self):
        assert self.pr.author == "alice"

    def test_state(self):
        assert self.pr.state == "open"

    def test_repository_derived_from_html_url(self):
        assert self.pr.repository == "acme/my-repo"

    def test_head_sha(self):
        assert self.pr.head_sha == "abc123def456"

    def test_base_branch(self):
        assert self.pr.base_branch == "main"

    def test_head_branch(self):
        assert self.pr.head_branch == "feature/fix-auth"

    def test_labels_extracted(self):
        assert self.pr.labels == ["bug", "priority:high"]

    def test_mergeable(self):
        assert self.pr.mergeable is True

    def test_draft_false(self):
        assert self.pr.draft is False

    def test_commits_count(self):
        assert self.pr.commits_count == 2

    def test_diff_summary_present(self):
        assert "diff --git" in self.pr.diff_summary


# ---------------------------------------------------------------------------
# Files normalisation
# ---------------------------------------------------------------------------

class TestNormalizeFiles:

    def setup_method(self):
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[ENRICHMENT],
            authenticated_user="alice",
        )
        self.files = ctx.pull_requests[0].files

    def test_file_count(self):
        assert len(self.files) == 2

    def test_first_file_filename(self):
        assert self.files[0].filename == "src/auth.py"

    def test_first_file_status(self):
        assert self.files[0].status == "modified"

    def test_second_file_status_added(self):
        assert self.files[1].status == "added"

    def test_additions_and_deletions(self):
        assert self.files[0].additions == 10
        assert self.files[0].deletions == 3
        assert self.files[0].changes == 13


# ---------------------------------------------------------------------------
# Review comments normalisation
# ---------------------------------------------------------------------------

class TestNormalizeReviewComments:

    def setup_method(self):
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[ENRICHMENT],
            authenticated_user="alice",
        )
        self.comments = ctx.pull_requests[0].review_comments

    def test_comment_count(self):
        assert len(self.comments) == 1

    def test_author(self):
        assert self.comments[0].author == "bob"

    def test_body(self):
        assert self.comments[0].body == "Please add a docstring."

    def test_path(self):
        assert self.comments[0].path == "src/auth.py"


# ---------------------------------------------------------------------------
# Reviews normalisation
# ---------------------------------------------------------------------------

class TestNormalizeReviews:

    def setup_method(self):
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[ENRICHMENT],
            authenticated_user="alice",
        )
        self.reviews = ctx.pull_requests[0].reviews

    def test_review_count(self):
        assert len(self.reviews) == 2

    def test_approved_review(self):
        approved = next(r for r in self.reviews if r.state == "APPROVED")
        assert approved.author == "carol"
        assert approved.submitted_at is not None

    def test_changes_requested_review(self):
        cr = next(r for r in self.reviews if r.state == "CHANGES_REQUESTED")
        assert cr.author == "dave"

    def test_pending_review_no_submitted_at(self):
        """A review with no submitted_at in raw data should produce None."""
        raw_pending = {"id": 999, "user": {"login": "eve"}, "state": "PENDING", "body": ""}
        enrichment_with_pending = {**ENRICHMENT, "reviews": [raw_pending]}
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[enrichment_with_pending],
            authenticated_user="alice",
        )
        review = ctx.pull_requests[0].reviews[0]
        assert review.submitted_at is None


# ---------------------------------------------------------------------------
# CI check runs normalisation
# ---------------------------------------------------------------------------

class TestNormalizeCheckRuns:

    def setup_method(self):
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[ENRICHMENT],
            authenticated_user="alice",
        )
        self.checks = ctx.pull_requests[0].ci_checks

    def test_check_count(self):
        assert len(self.checks) == 2

    def test_failing_check(self):
        failing = next(c for c in self.checks if c.name == "test-suite")
        assert failing.status == "completed"
        assert failing.conclusion == "failure"

    def test_passing_check(self):
        passing = next(c for c in self.checks if c.name == "lint")
        assert passing.conclusion == "success"

    def test_empty_check_runs(self):
        enrichment_no_ci = {**ENRICHMENT, "check_runs": {}}
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[enrichment_no_ci],
            authenticated_user="alice",
        )
        assert ctx.pull_requests[0].ci_checks == []


# ---------------------------------------------------------------------------
# Diff truncation
# ---------------------------------------------------------------------------

class TestTruncateDiff:

    def test_short_diff_not_truncated(self):
        norm = make_normalizer()
        diff = "diff --git a/f.py b/f.py\n"
        assert norm._truncate_diff(diff) == diff

    def test_long_diff_truncated(self):
        norm = make_normalizer()
        diff = "x" * (DIFF_TRUNCATE_CHARS + 500)
        result = norm._truncate_diff(diff)
        assert len(result) < len(diff)
        assert "[diff truncated]" in result

    def test_exact_length_not_truncated(self):
        norm = make_normalizer()
        diff = "y" * DIFF_TRUNCATE_CHARS
        assert norm._truncate_diff(diff) == diff

    def test_empty_diff_returns_empty(self):
        norm = make_normalizer()
        assert norm._truncate_diff("") == ""

    def test_none_like_empty_diff(self):
        norm = make_normalizer()
        assert norm._truncate_diff(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Defensive / missing field handling
# ---------------------------------------------------------------------------

class TestDefensiveNormalisation:

    def test_missing_pr_fields_do_not_raise(self):
        """Minimal PR dict — all optional fields absent — must not raise."""
        minimal_enrichment = {
            "pr": {"number": 1, "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z"},
        }
        ctx = make_normalizer().normalize(
            raw_search={},
            raw_pr_details=[minimal_enrichment],
            authenticated_user="alice",
        )
        pr = ctx.pull_requests[0]
        assert pr.number == 1
        assert pr.labels == []
        assert pr.files == []
        assert pr.ci_checks == []

    def test_missing_user_login_uses_empty_string(self):
        enrichment = {**ENRICHMENT, "pr": {**RAW_PR, "user": {}}}
        ctx = make_normalizer().normalize(
            raw_search=RAW_SEARCH,
            raw_pr_details=[enrichment],
            authenticated_user="alice",
        )
        assert ctx.pull_requests[0].author == ""
