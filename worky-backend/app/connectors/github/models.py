"""
app/connectors/github/models.py
==================================
Worky-internal Pydantic models for the GitHub connector.

These models represent the normalised GitHub data that GitHubNormalizer
produces and GitHubConnector places into ConnectorResult.data.  They are
internal domain models — not mirrors of the GitHub REST API response shapes.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • Pydantic

It must NOT import from any other app module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# File-level models
# ---------------------------------------------------------------------------

class PRFile(BaseModel):
    """
    Normalised representation of a single file changed in a PR.

    Fields
    ------
    filename : str
        Full path of the changed file (e.g., ``src/auth/service.py``).
    status : str
        Change type: ``"added"``, ``"removed"``, ``"modified"``, ``"renamed"``,
        ``"copied"``, ``"changed"``, or ``"unchanged"``.
    additions : int
        Lines added.
    deletions : int
        Lines deleted.
    changes : int
        Total changed lines (additions + deletions).
    """

    filename: str = Field(..., description="Full path of the changed file.")
    status: str = Field(default="modified", description="Change type.")
    additions: int = Field(default=0, description="Lines added.")
    deletions: int = Field(default=0, description="Lines deleted.")
    changes: int = Field(default=0, description="Total changed lines.")


# ---------------------------------------------------------------------------
# Review models
# ---------------------------------------------------------------------------

class ReviewComment(BaseModel):
    """
    Normalised representation of a single inline (line-level) review comment.

    Fields
    ------
    id : int
        GitHub comment ID.
    author : str
        GitHub username of the comment author.
    body : str
        Comment text.
    path : str
        File path the comment is attached to.
    created_at : datetime
        UTC timestamp when the comment was created.
    updated_at : datetime
        UTC timestamp of the last update.
    """

    id: int = Field(..., description="GitHub comment ID.")
    author: str = Field(default="", description="GitHub username of the author.")
    body: str = Field(default="", description="Comment text.")
    path: str = Field(default="", description="File path the comment is on.")
    created_at: datetime = Field(..., description="UTC creation timestamp.")
    updated_at: datetime = Field(..., description="UTC last-update timestamp.")


class PRReview(BaseModel):
    """
    Normalised representation of a top-level PR review.

    Fields
    ------
    id : int
        GitHub review ID.
    author : str
        GitHub username of the reviewer.
    state : str
        Review state: ``"APPROVED"``, ``"CHANGES_REQUESTED"``,
        ``"COMMENTED"``, or ``"PENDING"``.
    submitted_at : datetime | None
        UTC timestamp when the review was submitted.  None when the review
        is still in PENDING state (never submitted).
    body : str
        Optional review summary text.
    """

    id: int = Field(..., description="GitHub review ID.")
    author: str = Field(default="", description="GitHub username of the reviewer.")
    state: str = Field(default="PENDING", description="Review state.")
    submitted_at: Optional[datetime] = Field(
        default=None, description="UTC submission timestamp."
    )
    body: str = Field(default="", description="Review summary text.")


# ---------------------------------------------------------------------------
# CI models
# ---------------------------------------------------------------------------

class CICheckRun(BaseModel):
    """
    Normalised representation of a single CI check-run.

    Fields
    ------
    name : str
        Name of the check (e.g., ``"test-suite"``, ``"lint"``, ``"build"``).
    status : str
        Execution status: ``"queued"``, ``"in_progress"``, or ``"completed"``.
    conclusion : str | None
        Final result when status is ``"completed"``:
        ``"success"``, ``"failure"``, ``"neutral"``, ``"cancelled"``,
        ``"skipped"``, ``"timed_out"``, or ``"action_required"``.
        None when the check has not yet completed.
    started_at : datetime | None
        UTC timestamp when the check started.  None if not yet started.
    completed_at : datetime | None
        UTC timestamp when the check finished.  None if not yet completed.
    """

    name: str = Field(..., description="Name of the check.")
    status: str = Field(default="queued", description="Execution status.")
    conclusion: Optional[str] = Field(
        default=None, description="Final result (only set when completed)."
    )
    started_at: Optional[datetime] = Field(
        default=None, description="UTC start timestamp."
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="UTC completion timestamp."
    )


# ---------------------------------------------------------------------------
# Pull request model
# ---------------------------------------------------------------------------

class PullRequest(BaseModel):
    """
    Fully enriched, normalised representation of a GitHub pull request.

    Core fields are populated from ``get_pull_request()``.  Enrichment
    fields (files, reviews, ci_checks, etc.) are populated by subsequent
    sub-fetches run concurrently by GitHubConnector.

    Fields
    ------
    number : int
        PR number within the repository.
    title : str
        PR title.
    body : str
        PR description body (may be empty).
    author : str
        GitHub login of the PR author.
    state : str
        PR state: ``"open"`` or ``"closed"``.
    html_url : str
        Full URL to the PR on GitHub.
    base_branch : str
        Target branch (e.g., ``"main"``).
    head_branch : str
        Source branch (e.g., ``"feature/my-feature"``).
    head_sha : str
        HEAD commit SHA of the source branch.  Used for CI status lookup.
    created_at : datetime
        UTC creation timestamp.
    updated_at : datetime
        UTC last-update timestamp.
    labels : list[str]
        Label names applied to the PR.
    mergeable : bool | None
        Whether GitHub considers the PR mergeable.  None means GitHub has
        not yet computed the mergeability (typically for recently-created
        or recently-updated PRs).
    draft : bool
        True when the PR is a draft.
    repository : str
        Fully-qualified repository name in ``"owner/repo"`` format.

    --- Enriched fields (populated by sub-fetches) ---

    files : list[PRFile]
        All files changed by the PR.
    commits_count : int
        Number of commits in the PR.
    review_comments : list[ReviewComment]
        Inline (line-level) review comments.
    reviews : list[PRReview]
        Top-level PR reviews (APPROVED, CHANGES_REQUESTED, …).
    ci_checks : list[CICheckRun]
        CI check-run results for the head commit.
    diff_summary : str
        First 2 000 characters of the unified diff.  Truncated to keep
        the IBM Bob prompt within token limits.
    """

    number: int = Field(..., description="PR number within the repository.")
    title: str = Field(default="", description="PR title.")
    body: str = Field(default="", description="PR description body.")
    author: str = Field(default="", description="GitHub login of the PR author.")
    state: str = Field(default="open", description="PR state.")
    html_url: str = Field(default="", description="Full PR URL.")
    base_branch: str = Field(default="", description="Target branch.")
    head_branch: str = Field(default="", description="Source branch.")
    head_sha: str = Field(default="", description="HEAD commit SHA.")
    created_at: datetime = Field(..., description="UTC creation timestamp.")
    updated_at: datetime = Field(..., description="UTC last-update timestamp.")
    labels: list[str] = Field(default_factory=list, description="Applied label names.")
    mergeable: Optional[bool] = Field(
        default=None, description="GitHub mergeability verdict."
    )
    draft: bool = Field(default=False, description="True when the PR is a draft.")
    repository: str = Field(
        default="", description="Fully-qualified repository name (owner/repo)."
    )

    # Enriched fields
    files: list[PRFile] = Field(
        default_factory=list, description="Changed files."
    )
    commits_count: int = Field(
        default=0, description="Number of commits in the PR."
    )
    review_comments: list[ReviewComment] = Field(
        default_factory=list, description="Inline review comments."
    )
    reviews: list[PRReview] = Field(
        default_factory=list, description="Top-level PR reviews."
    )
    ci_checks: list[CICheckRun] = Field(
        default_factory=list, description="CI check-run results."
    )
    diff_summary: str = Field(
        default="",
        description="First 2 000 chars of the unified diff (truncated).",
    )

    model_config = {"frozen": False}


# ---------------------------------------------------------------------------
# Top-level context model
# ---------------------------------------------------------------------------

class GitHubContext(BaseModel):
    """
    The normalised GitHub payload assembled by GitHubNormalizer.

    This is the object that GitHubConnector places into ConnectorResult.data
    via model_dump().

    Fields
    ------
    pull_requests : list[PullRequest]
        All enriched pull requests relevant to the authenticated user.

    total_prs_found : int
        Total number of PRs returned by the search query (may exceed the
        number of enriched PRs when capped by GITHUB_MAX_PRS).

    authenticated_user : str
        GitHub login of the authenticated user.  Used for classifying PRs
        into widget card categories (authored / review requested / assigned).
    """

    pull_requests: list[PullRequest] = Field(
        default_factory=list,
        description="Enriched pull requests relevant to the user.",
    )
    total_prs_found: int = Field(
        default=0,
        description="Total matches from the search query.",
    )
    authenticated_user: str = Field(
        default="",
        description="GitHub login of the authenticated user.",
    )

    model_config = {"frozen": False}
