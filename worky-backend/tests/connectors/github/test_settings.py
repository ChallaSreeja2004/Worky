"""
tests/connectors/github/test_settings.py
=========================================
Unit tests for GitHubSettings.

Specifically covers the empty-string fallback for GITHUB_API_BASE_URL
that caused the "missing protocol" error when the env var was present
but blank in .env (GITHUB_API_BASE_URL=).
"""

from __future__ import annotations

from app.connectors.github.settings import GitHubSettings


class TestGitHubSettingsBaseUrl:

    def test_default_base_url_when_not_provided(self):
        """When GITHUB_API_BASE_URL is not supplied, the default is used."""
        settings = GitHubSettings(github_access_token="ghp_test")
        assert settings.github_api_base_url == "https://api.github.com"

    def test_empty_string_falls_back_to_default(self):
        """GITHUB_API_BASE_URL= (empty string in .env) must not produce an empty base URL."""
        settings = GitHubSettings(
            github_access_token="ghp_test",
            github_api_base_url="",
        )
        assert settings.github_api_base_url == "https://api.github.com"

    def test_whitespace_only_falls_back_to_default(self):
        """A whitespace-only value is also treated as unset."""
        settings = GitHubSettings(
            github_access_token="ghp_test",
            github_api_base_url="   ",
        )
        assert settings.github_api_base_url == "https://api.github.com"

    def test_explicit_value_is_used(self):
        """A real URL override is preserved."""
        settings = GitHubSettings(
            github_access_token="ghp_test",
            github_api_base_url="https://github.example.com/api/v3",
        )
        assert settings.github_api_base_url == "https://github.example.com/api/v3"

    def test_trailing_slash_is_stripped(self):
        """Trailing slash is stripped so URL paths never produce double-slashes."""
        settings = GitHubSettings(
            github_access_token="ghp_test",
            github_api_base_url="https://api.github.com/",
        )
        assert settings.github_api_base_url == "https://api.github.com"
