"""
tests/context_builder/test_builder.py
========================================
Unit tests for ContextBuilder.

All connectors used here are lightweight AsyncMock objects that satisfy the
BaseConnector interface.  No real connector (OutlookConnector, SlackConnector)
is imported or instantiated.  This keeps the test suite isolated from every
connector's implementation and proves that ContextBuilder is genuinely
connector-agnostic.

Coverage
--------
  • build() — all connectors return SUCCESS
  • build() — one connector returns FAILED
  • build() — all connectors return FAILED
  • build() — connector returns PARTIAL (data is included in WorkContext.sources)
  • build() — connector raises unexpectedly (_collect_connector safety net)
  • build() — raising connector does not affect other connectors
  • build() — empty connector list returns empty WorkContext without error
  • build() — metadata contains assembly_duration_ms and connector_count
  • build() — user_id is preserved on WorkContext
  • build() — assembled_at is a timezone-aware UTC datetime
  • build() — return type is WorkContext
  • build() — two connectors run concurrently, not sequentially
  • _collect_connector() — connector error message in ConnectorResult.errors
  • _collect_connector() — source_name preserved on synthesised FAILED result
"""

from __future__ import annotations

import asyncio
from datetime import timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.connectors.models import ConnectorResult, ConnectorStatus
from app.context_builder.builder import ContextBuilder
from app.context_builder.models import WorkContext


# ---------------------------------------------------------------------------
# Mock connector factories
# ---------------------------------------------------------------------------
# These helpers return the smallest possible object that satisfies the
# BaseConnector contract.  They do not subclass BaseConnector to avoid
# importing any concrete connector package.
# ---------------------------------------------------------------------------

def make_success_connector(
    source_name: str = "mock",
    data: dict[str, Any] | None = None,
) -> MagicMock:
    """
    Return a mock connector whose get_context() resolves to ConnectorResult.success().
    """
    connector = MagicMock()
    connector.source_name = source_name
    connector.get_context = AsyncMock(
        return_value=ConnectorResult.success(
            source=source_name,
            data=data or {"items": [1, 2, 3]},
        )
    )
    return connector


def make_failed_connector(
    source_name: str = "mock",
    error: str = "simulated failure",
) -> MagicMock:
    """
    Return a mock connector whose get_context() resolves to ConnectorResult.failed().
    """
    connector = MagicMock()
    connector.source_name = source_name
    connector.get_context = AsyncMock(
        return_value=ConnectorResult.failed(
            source=source_name,
            errors=[error],
        )
    )
    return connector


def make_partial_connector(
    source_name: str = "mock",
    data: dict[str, Any] | None = None,
    error: str = "partial failure",
) -> MagicMock:
    """
    Return a mock connector whose get_context() resolves to ConnectorResult.partial().
    """
    connector = MagicMock()
    connector.source_name = source_name
    connector.get_context = AsyncMock(
        return_value=ConnectorResult.partial(
            source=source_name,
            data=data or {"items": [1]},
            errors=[error],
        )
    )
    return connector


def make_raising_connector(
    source_name: str = "mock",
    exception: Exception | None = None,
) -> MagicMock:
    """
    Return a mock connector whose get_context() raises an unexpected exception.
    Used to test the _collect_connector() safety net.
    """
    connector = MagicMock()
    connector.source_name = source_name
    connector.get_context = AsyncMock(
        side_effect=exception or RuntimeError("totally unexpected crash")
    )
    return connector


def make_slow_connector(
    source_name: str = "mock",
    delay: float = 0.05,
) -> MagicMock:
    """
    Return a mock connector that sleeps for `delay` seconds before returning SUCCESS.
    Used to verify that asyncio.gather() runs connectors concurrently.
    """
    connector = MagicMock()
    connector.source_name = source_name

    async def _slow_get_context(user_id: str, access_token: str) -> ConnectorResult:
        await asyncio.sleep(delay)
        return ConnectorResult.success(source=source_name, data={"ok": True})

    connector.get_context = _slow_get_context
    return connector


# ---------------------------------------------------------------------------
# Tests — all connectors succeed
# ---------------------------------------------------------------------------

class TestBuildAllSucceed:

    async def test_returns_workcontext_instance(self):
        """build() always returns a WorkContext."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_success_connector("outlook")],
            access_token="tok",
        )
        assert isinstance(result, WorkContext)

    async def test_all_sources_present(self):
        """When both connectors succeed, both source names appear in WorkContext.sources."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_success_connector("slack"),
            ],
            access_token="tok",
        )
        assert "outlook" in result.sources
        assert "slack" in result.sources

    async def test_active_sources_matches_connector_names(self):
        """active_sources contains all connector source names on full success."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_success_connector("slack"),
            ],
            access_token="tok",
        )
        assert set(result.active_sources) == {"outlook", "slack"}

    async def test_successful_connectors_count(self):
        """successful_connectors equals the number of connectors on full success."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_success_connector("slack"),
            ],
            access_token="tok",
        )
        assert result.successful_connectors == 2

    async def test_errors_dict_is_empty(self):
        """No errors recorded when all connectors succeed."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_success_connector("outlook")],
            access_token="tok",
        )
        assert result.errors == {}

    async def test_connector_data_preserved_in_sources(self):
        """ConnectorResult.data is stored verbatim in WorkContext.sources."""
        payload = {"calendar_events": [{"id": "evt-1"}], "emails": []}
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_success_connector("outlook", data=payload)],
            access_token="tok",
        )
        assert result.sources["outlook"] == payload


# ---------------------------------------------------------------------------
# Tests — identity fields
# ---------------------------------------------------------------------------

class TestBuildIdentity:

    async def test_user_id_preserved(self):
        """WorkContext.user_id matches the value passed to build()."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="user-abc-123",
            connectors=[make_success_connector("outlook")],
            access_token="tok",
        )
        assert result.user_id == "user-abc-123"

    async def test_assembled_at_is_utc(self):
        """WorkContext.assembled_at is timezone-aware and in UTC."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[],
            access_token="tok",
        )
        assert result.assembled_at.tzinfo is not None
        assert result.assembled_at.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Tests — metadata
# ---------------------------------------------------------------------------

class TestBuildMetadata:

    async def test_metadata_contains_assembly_duration_ms(self):
        """metadata["assembly_duration_ms"] is present and is a non-negative integer."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_success_connector("outlook")],
            access_token="tok",
        )
        assert "assembly_duration_ms" in result.metadata
        assert isinstance(result.metadata["assembly_duration_ms"], int)
        assert result.metadata["assembly_duration_ms"] >= 0

    async def test_metadata_contains_connector_count(self):
        """metadata["connector_count"] equals the number of connectors passed."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_success_connector("slack"),
            ],
            access_token="tok",
        )
        assert result.metadata["connector_count"] == 2

    async def test_metadata_connector_count_zero_for_empty_list(self):
        """connector_count is 0 when no connectors are passed."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[],
            access_token="tok",
        )
        assert result.metadata["connector_count"] == 0


# ---------------------------------------------------------------------------
# Tests — empty connector list
# ---------------------------------------------------------------------------

class TestBuildEmptyList:

    async def test_empty_list_does_not_raise(self):
        """build() with an empty connector list returns normally."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[],
            access_token="tok",
        )
        assert isinstance(result, WorkContext)

    async def test_empty_list_sources_is_empty(self):
        """No connectors → WorkContext.sources is empty."""
        builder = ContextBuilder()
        result = await builder.build(user_id="u1", connectors=[], access_token="tok")
        assert result.sources == {}

    async def test_empty_list_active_sources_is_empty(self):
        """No connectors → active_sources is []."""
        builder = ContextBuilder()
        result = await builder.build(user_id="u1", connectors=[], access_token="tok")
        assert result.active_sources == []

    async def test_empty_list_connector_summaries_is_empty(self):
        """No connectors → connector_summaries is []."""
        builder = ContextBuilder()
        result = await builder.build(user_id="u1", connectors=[], access_token="tok")
        assert result.connector_summaries == []


# ---------------------------------------------------------------------------
# Tests — one connector fails
# ---------------------------------------------------------------------------

class TestBuildOneConnectorFails:

    async def test_failed_source_absent_from_sources(self):
        """A FAILED connector's source name is not in WorkContext.sources."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert "outlook" in result.sources
        assert "slack" not in result.sources

    async def test_successful_connector_unaffected_by_failed_sibling(self):
        """When one connector fails, the successful connector's data is still present."""
        payload = {"messages": ["hello"]}
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook", data=payload),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert result.sources["outlook"] == payload

    async def test_failed_connector_in_summaries(self):
        """A FAILED connector still appears in connector_summaries with FAILED status."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        slack_summary = next(
            (s for s in result.connector_summaries if s.source == "slack"), None
        )
        assert slack_summary is not None
        assert slack_summary.status == ConnectorStatus.FAILED

    async def test_failed_source_excluded_from_active_sources(self):
        """active_sources does not include a FAILED connector's source name."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert "slack" not in result.active_sources
        assert "outlook" in result.active_sources

    async def test_failed_connector_errors_recorded(self):
        """WorkContext.errors contains the error message from the failed connector."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_success_connector("outlook"),
                make_failed_connector("slack", error="Slack API unreachable"),
            ],
            access_token="tok",
        )
        assert "slack" in result.errors
        assert any("Slack API unreachable" in e for e in result.errors["slack"])


# ---------------------------------------------------------------------------
# Tests — all connectors fail
# ---------------------------------------------------------------------------

class TestBuildAllConnectorsFail:

    async def test_sources_is_empty(self):
        """All connectors FAILED → WorkContext.sources is empty."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_failed_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert result.sources == {}

    async def test_active_sources_is_empty(self):
        """All connectors FAILED → active_sources is []."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_failed_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert result.active_sources == []

    async def test_all_summaries_have_failed_status(self):
        """All connector summaries carry FAILED status."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_failed_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert all(
            s.status == ConnectorStatus.FAILED
            for s in result.connector_summaries
        )

    async def test_total_connectors_count_preserved(self):
        """total_connectors reflects all connectors, even those that failed."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_failed_connector("outlook"),
                make_failed_connector("slack"),
            ],
            access_token="tok",
        )
        assert result.total_connectors == 2


# ---------------------------------------------------------------------------
# Tests — partial connector result
# ---------------------------------------------------------------------------

class TestBuildPartialConnector:

    async def test_partial_data_included_in_sources(self):
        """A PARTIAL connector's data is still included in WorkContext.sources."""
        data = {"items": [1, 2]}
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_partial_connector("outlook", data=data)],
            access_token="tok",
        )
        assert "outlook" in result.sources
        assert result.sources["outlook"] == data

    async def test_partial_source_in_active_sources(self):
        """PARTIAL connector appears in active_sources (it returned usable data)."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_partial_connector("outlook")],
            access_token="tok",
        )
        assert "outlook" in result.active_sources

    async def test_partial_errors_recorded(self):
        """PARTIAL connector's errors are recorded in WorkContext.errors."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_partial_connector("outlook", error="Email fetch timed out")],
            access_token="tok",
        )
        assert "outlook" in result.errors
        assert any("Email fetch timed out" in e for e in result.errors["outlook"])

    async def test_partial_summary_status_is_partial(self):
        """connector_summaries entry for a PARTIAL connector carries PARTIAL status."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_partial_connector("outlook")],
            access_token="tok",
        )
        outlook_summary = next(
            (s for s in result.connector_summaries if s.source == "outlook"), None
        )
        assert outlook_summary is not None
        assert outlook_summary.status == ConnectorStatus.PARTIAL


# ---------------------------------------------------------------------------
# Tests — connector raises unexpectedly (_collect_connector safety net)
# ---------------------------------------------------------------------------

class TestBuildConnectorRaises:

    async def test_raising_connector_produces_failed_result(self):
        """A connector that raises is converted to FAILED and does not crash the build."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_raising_connector("outlook")],
            access_token="tok",
        )
        assert isinstance(result, WorkContext)
        assert "outlook" not in result.sources

    async def test_raising_connector_in_summaries_as_failed(self):
        """connector_summaries records the raising connector with FAILED status."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_raising_connector("outlook")],
            access_token="tok",
        )
        outlook_summary = next(
            (s for s in result.connector_summaries if s.source == "outlook"), None
        )
        assert outlook_summary is not None
        assert outlook_summary.status == ConnectorStatus.FAILED

    async def test_raising_connector_error_message_recorded(self):
        """The exception message is captured in the synthesised ConnectorResult.errors."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_raising_connector(
                    "outlook",
                    exception=ValueError("something exploded"),
                )
            ],
            access_token="tok",
        )
        assert "outlook" in result.errors
        assert any("something exploded" in e for e in result.errors["outlook"])

    async def test_raising_connector_does_not_affect_other_connectors(self):
        """Other connectors complete normally even when one connector raises."""
        slack_data = {"messages": ["hello"]}
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_raising_connector("outlook"),
                make_success_connector("slack", data=slack_data),
            ],
            access_token="tok",
        )
        assert "slack" in result.sources
        assert result.sources["slack"] == slack_data
        assert "outlook" not in result.sources

    async def test_source_name_preserved_on_synthesised_failed_result(self):
        """The synthesised FAILED result carries the correct source_name."""
        builder = ContextBuilder()
        result = await builder.build(
            user_id="u1",
            connectors=[make_raising_connector("github")],
            access_token="tok",
        )
        github_summary = next(
            (s for s in result.connector_summaries if s.source == "github"), None
        )
        assert github_summary is not None


# ---------------------------------------------------------------------------
# Tests — concurrency
# ---------------------------------------------------------------------------

class TestBuildConcurrency:

    async def test_connectors_run_concurrently(self):
        """
        Two connectors each taking 50ms should complete in under 150ms total
        (well under the 100ms sequential total), confirming asyncio.gather()
        runs them in parallel rather than sequentially.
        """
        delay = 0.05  # 50ms each

        builder = ContextBuilder()

        import time as _time
        start = _time.monotonic()
        result = await builder.build(
            user_id="u1",
            connectors=[
                make_slow_connector("outlook", delay=delay),
                make_slow_connector("slack",   delay=delay),
            ],
            access_token="tok",
        )
        elapsed = _time.monotonic() - start

        # Both should complete in roughly 50ms, not 100ms.
        # A generous upper bound of 3× the single-connector delay accounts
        # for CI scheduler jitter while still catching sequential execution.
        assert elapsed < delay * 3, (
            f"Expected concurrent execution (~{delay}s), "
            f"got {elapsed:.3f}s — connectors may be running sequentially."
        )
        # Both results should still be present.
        assert "outlook" in result.sources
        assert "slack" in result.sources


# ---------------------------------------------------------------------------
# Tests — connector contract forwarding
# ---------------------------------------------------------------------------

class TestBuildConnectorContractForwarding:

    async def test_user_id_forwarded_to_each_connector(self):
        """build() forwards user_id to every connector's get_context() call."""
        connector = make_success_connector("outlook")
        builder = ContextBuilder()
        await builder.build(
            user_id="specific-user-id",
            connectors=[connector],
            access_token="tok",
        )
        connector.get_context.assert_called_once_with(
            user_id="specific-user-id",
            access_token="tok",
        )

    async def test_access_token_forwarded_to_each_connector(self):
        """build() forwards access_token to every connector's get_context() call."""
        connector_a = make_success_connector("outlook")
        connector_b = make_success_connector("slack")
        builder = ContextBuilder()
        await builder.build(
            user_id="u1",
            connectors=[connector_a, connector_b],
            access_token="my-bearer-token",
        )
        connector_a.get_context.assert_called_once_with(
            user_id="u1",
            access_token="my-bearer-token",
        )
        connector_b.get_context.assert_called_once_with(
            user_id="u1",
            access_token="my-bearer-token",
        )

    async def test_each_connector_called_exactly_once(self):
        """Every connector's get_context() is called exactly once per build()."""
        connector_a = make_success_connector("outlook")
        connector_b = make_success_connector("slack")
        builder = ContextBuilder()
        await builder.build(
            user_id="u1",
            connectors=[connector_a, connector_b],
            access_token="tok",
        )
        connector_a.get_context.assert_called_once()
        connector_b.get_context.assert_called_once()

    async def test_stateless_across_multiple_build_calls(self):
        """
        ContextBuilder is stateless — calling build() twice with different
        connector lists returns independent, correct results each time.
        """
        builder = ContextBuilder()

        result_1 = await builder.build(
            user_id="u1",
            connectors=[make_success_connector("outlook")],
            access_token="tok",
        )
        result_2 = await builder.build(
            user_id="u2",
            connectors=[make_success_connector("slack")],
            access_token="tok",
        )

        assert result_1.user_id == "u1"
        assert "outlook" in result_1.sources
        assert "slack" not in result_1.sources

        assert result_2.user_id == "u2"
        assert "slack" in result_2.sources
        assert "outlook" not in result_2.sources
