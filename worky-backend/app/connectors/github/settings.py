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

from pydantic_settings import BaseSettings, SettingsConfigDict


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
      GITHUB_REQUEST_TIMEOUT — Per-request timeout in seconds. Defaults to 20.0.
      GITHUB_MAX_PRS        — Maximum number of PRs to fetch and enrich per run.
                              Caps cost when a user has many open PRs.
                              Defaults to 20.
    """

    github_access_token: str

    github_api_base_url: str = "https://api.github.com"
    github_request_timeout: float = 20.0
    github_max_prs: int = 20

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
