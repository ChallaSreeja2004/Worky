"""
app/connectors/github/settings.py
===================================
GitHubSettings — GitHub-specific configuration loaded from .env.

Reads GITHUB_ACCESS_TOKEN (and optional overrides) from the environment.
The access token is a GitHub Personal Access Token (PAT) with the
``repo`` scope, or a delegated OAuth token from a GitHub OAuth App.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • pydantic-settings

It must NOT import from any other app module.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_BASE_URL = "https://api.github.com"


class GitHubSettings(BaseSettings):
    """
    GitHub configuration loaded from environment variables.

    Required variables (must be set in .env or environment):
      GITHUB_ACCESS_TOKEN   — Personal Access Token (ghp_...) or OAuth token.
                              Required scope: ``repo`` (or ``public_repo`` for
                              public repositories only).

    Optional variables:
      GITHUB_API_BASE_URL   — Override the GitHub REST API base URL.
                              Useful for GitHub Enterprise Server deployments.
                              Defaults to https://api.github.com.
                              An empty string is treated as unset and falls
                              back to the default.
      GITHUB_REQUEST_TIMEOUT — Per-request timeout in seconds. Defaults to 20.0.
      GITHUB_MAX_PRS        — Maximum number of PRs to fetch and enrich per run.
                              Caps cost when a user has many open PRs.
                              Defaults to 20.
    """

    github_access_token: str

    github_api_base_url: str = _DEFAULT_BASE_URL
    github_request_timeout: float = 20.0
    github_max_prs: int = 20

    @field_validator("github_api_base_url", mode="before")
    @classmethod
    def _default_base_url_when_empty(cls, v: str) -> str:
        """
        Treat an empty GITHUB_API_BASE_URL as unset.

        pydantic-settings passes an empty string through unchanged when the
        env var is present but blank (``GITHUB_API_BASE_URL=``).  Without
        this validator the field would be set to "" and every API request
        would fail with a missing-protocol error.
        """
        if not v or not v.strip():
            return _DEFAULT_BASE_URL
        return v.rstrip("/")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_github_settings() -> GitHubSettings:
    """
    Return a cached singleton GitHubSettings instance.

    lru_cache ensures the .env file is read only once per process lifetime.
    Call get_github_settings.cache_clear() in tests to reset between cases.
    """
    return GitHubSettings()
