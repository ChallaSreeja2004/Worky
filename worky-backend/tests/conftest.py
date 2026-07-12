"""
tests/conftest.py
=================
Shared pytest fixtures for the Worky backend test suite.

Fixtures defined here are available to all test modules without import.
"""

import pytest
from cryptography.fernet import Fernet

from app.auth.repository import InMemoryTokenRepository


@pytest.fixture
def token_repository() -> InMemoryTokenRepository:
    """A fresh InMemoryTokenRepository for each test."""
    return InMemoryTokenRepository()


@pytest.fixture
def encryption_key() -> str:
    """A valid Fernet key for tests that need one."""
    return Fernet.generate_key().decode()
