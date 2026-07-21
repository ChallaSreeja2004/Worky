"""
tests/connectors/github/test_models.py
=======================================
Unit tests for GitHubConnector Pydantic models.

Coverage:
  • PullRequest validates required fields correctly.
  • Default values are applied when optional fields are absent.
  • GitHubContext aggregates pull_requests, total_prs_found, authenticated_user.
  • model_dump() output is JSON-serialisable (no datetime objects in serialised form).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.connectors.github.models import (
    CICheckRun,
    GitHubContext,
    PRFile,
    PRReview,
    PullRequest,
    ReviewComment,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)


def make_pr(**overrides) -> PullRequest:
    defaults = dict(
        number=42,
        title="Fix auth bug",
        body="This PR fixes the login issue.",
        author="alice",
        state="open",
        html_url="https://github.com/acme/my-repo/pull/42",
        base_branch="main",
        head_branch="feature/fix-auth",
        head_sha="abc123",
        created_at=NOW,
        updated_at=NOW,
        labels=["bug", "priority:high"],
        mergeable=True,
        draft=False,
        repository="acme/my-repo",
    )
    defaults.update(overrides)
    return PullRequest(**defaults)


# ---------------------------------------------------------------------------
# PullRequest model tests
# ---------------------------------------------------------------------------

class TestPullRequestModel:

    def test_required_fields_set(self):
        pr = make_pr()
        assert pr.number == 42
        assert pr.author == "alice"
        assert pr.repository == "acme/my-repo"

    def test_labels_stored_as_list(self):
        pr = make_pr(labels=["bug", "wip"])
        assert pr.labels == ["bug", "wip"]

    def test_empty_labels_default(self):
        pr = make_pr(labels=[])
        assert pr.labels == []

    def test_mergeable_can_be_none(self):
        pr = make_pr(mergeable=None)
        assert pr.mergeable is None

    def test_draft_default_false(self):
        pr = make_pr()
        assert pr.draft is False

    def test_enriched_fields_default_empty(self):
        pr = make_pr()
        assert pr.files == []
        assert pr.commits_count == 0
        assert pr.review_comments == []
        assert pr.reviews == []
        assert pr.ci_checks == []
        assert pr.diff_summary == ""

    def test_pr_with_enrichment(self):
        pr = make_pr(
            files=[PRFile(filename="src/auth.py", status="modified", additions=5, deletions=2, changes=7)],
            commits_count=3,
            diff_summary="diff --git a/src/auth.py...",
        )
        assert len(pr.files) == 1
        assert pr.files[0].filename == "src/auth.py"
        assert pr.commits_count == 3

    def test_model_dump_is_dict(self):
        pr = make_pr()
        dumped = pr.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["number"] == 42


# ---------------------------------------------------------------------------
# PRFile model tests
# ---------------------------------------------------------------------------

class TestPRFileModel:

    def test_required_filename(self):
        f = PRFile(filename="src/main.py", status="modified", additions=1, deletions=0, changes=1)
        assert f.filename == "src/main.py"

    def test_defaults(self):
        f = PRFile(filename="readme.md")
        assert f.status == "modified"
        assert f.additions == 0
        assert f.deletions == 0
        assert f.changes == 0


# ---------------------------------------------------------------------------
# ReviewComment model tests
# ---------------------------------------------------------------------------

class TestReviewCommentModel:

    def test_fields(self):
        comment = ReviewComment(
            id=1,
            author="bob",
            body="Please add a test.",
            path="src/auth.py",
            created_at=NOW,
            updated_at=NOW,
        )
        assert comment.id == 1
        assert comment.author == "bob"
        assert comment.path == "src/auth.py"

    def test_empty_body_allowed(self):
        comment = ReviewComment(id=2, created_at=NOW, updated_at=NOW)
        assert comment.body == ""


# ---------------------------------------------------------------------------
# PRReview model tests
# ---------------------------------------------------------------------------

class TestPRReviewModel:

    def test_approved_review(self):
        review = PRReview(id=10, author="carol", state="APPROVED", submitted_at=NOW)
        assert review.state == "APPROVED"
        assert review.submitted_at == NOW

    def test_pending_review_has_no_submitted_at(self):
        review = PRReview(id=11, author="dave", state="PENDING")
        assert review.submitted_at is None


# ---------------------------------------------------------------------------
# CICheckRun model tests
# ---------------------------------------------------------------------------

class TestCICheckRunModel:

    def test_completed_check(self):
        check = CICheckRun(
            name="test-suite",
            status="completed",
            conclusion="failure",
            started_at=NOW,
            completed_at=NOW,
        )
        assert check.status == "completed"
        assert check.conclusion == "failure"

    def test_pending_check_defaults(self):
        check = CICheckRun(name="build")
        assert check.status == "queued"
        assert check.conclusion is None
        assert check.started_at is None
        assert check.completed_at is None


# ---------------------------------------------------------------------------
# GitHubContext model tests
# ---------------------------------------------------------------------------

class TestGitHubContextModel:

    def test_empty_context(self):
        ctx = GitHubContext()
        assert ctx.pull_requests == []
        assert ctx.total_prs_found == 0
        assert ctx.authenticated_user == ""

    def test_populated_context(self):
        pr = make_pr()
        ctx = GitHubContext(
            pull_requests=[pr],
            total_prs_found=5,
            authenticated_user="alice",
        )
        assert len(ctx.pull_requests) == 1
        assert ctx.total_prs_found == 5
        assert ctx.authenticated_user == "alice"

    def test_model_dump_serialisable(self):
        pr = make_pr()
        ctx = GitHubContext(pull_requests=[pr], total_prs_found=1, authenticated_user="alice")
        dumped = ctx.model_dump()
        assert isinstance(dumped, dict)
        assert len(dumped["pull_requests"]) == 1
