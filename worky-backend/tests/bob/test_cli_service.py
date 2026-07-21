"""
tests/bob/test_cli_service.py
==============================
Unit tests for BobCLIService.

All subprocess calls are mocked — no live Bob Shell invocations are made.
These tests verify that BobCLIService:

  • Is a concrete subclass of BobService.
  • Raises BobConfigError at construction when bob executable is not found.
  • Builds and parses a well-formed stream-json response into a RecommendationSet.
  • Strips markdown fences from the completion output.
  • Raises BobTimeoutError when asyncio.wait_for times out.
  • Raises BobServiceError when the stream result event reports an error.
  • Raises BobResponseError when no attempt_completion tool_result is present.
  • Raises BobResponseError when the completion output is not valid JSON.
  • Raises BobResponseError when the JSON is not an array.
  • Raises BobResponseError when a recommendation item fails Pydantic validation.
  • Preserves user_id from WorkContext in the returned RecommendationSet.
  • Sets model_version to "bob-cli-v1".
  • Includes active_sources and request_id in metadata.

stream-json format verified against live Bob Shell output.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bob.cli_service import (
    BobCLIService,
    _build_prompt,
    _extract_completion_output,
    _local_timezone_name,
    _parse_recommendations,
)
from app.bob.models import Recommendation, RecommendationSet
from app.bob.service import (
    BobConfigError,
    BobResponseError,
    BobService,
    BobServiceError,
    BobTimeoutError,
)
from app.connectors.models import ConnectorResult
from app.context_builder.models import WorkContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_work_context(
    user_id: str = "user-001",
    active_source_names: list[str] | None = None,
) -> WorkContext:
    if not active_source_names:
        return WorkContext(user_id=user_id)
    results = [
        ConnectorResult.success(source=s, data={"items": []})
        for s in active_source_names
    ]
    return WorkContext.from_connector_results(user_id=user_id, results=results)


def make_stream_json(recommendations: list[dict]) -> bytes:
    """
    Build a minimal but structurally correct stream-json output matching the
    format emitted by Bob Shell (verified against live output).
    """
    answer_json = json.dumps(recommendations)
    lines = [
        json.dumps({"type": "init", "session_id": "test-session"}),
        json.dumps({"type": "message", "role": "user", "content": "...", "delta": True}),
        json.dumps({
            "type": "tool_use",
            "tool_name": "attempt_completion",
            "tool_id": "tool-1",
            "parameters": {"result": answer_json},
        }),
        json.dumps({
            "type": "tool_result",
            "tool_id": "tool-1",
            "status": "success",
            "output": answer_json,
        }),
        json.dumps({
            "type": "result",
            "status": "success",
            "stats": {"total_tokens": 100, "duration_ms": 5000},
        }),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_valid_recommendation_list() -> list[dict]:
    return [
        {
            "priority": 1,
            "category": "email",
            "title": "Review unread emails",
            "description": "You have unread high-importance emails.",
            "action_url": "https://outlook.office.com/mail",
            "source": "outlook",
        }
    ]


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

class TestBobCLIServiceIsABobService:

    def test_is_subclass_of_bob_service(self):
        assert issubclass(BobCLIService, BobService)

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    def test_instance_is_bob_service(self, _):
        service: BobService = BobCLIService()
        assert isinstance(service, BobService)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestBobCLIServiceConstructor:

    @patch("shutil.which", return_value=None)
    def test_raises_bob_config_error_when_executable_not_found(self, _):
        """shutil.which returning None raises BobConfigError."""
        with pytest.raises(BobConfigError) as exc_info:
            BobCLIService(bob_executable="bob")
        assert "not found" in exc_info.value.message

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    def test_constructs_successfully_when_executable_found(self, _):
        service = BobCLIService()
        assert service is not None

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    def test_stores_resolved_executable_path(self, mock_which):
        mock_which.return_value = "/custom/path/bob"
        service = BobCLIService(bob_executable="bob")
        assert service._bob_executable == "/custom/path/bob"


# ---------------------------------------------------------------------------
# Successful analyze() calls
# ---------------------------------------------------------------------------

class TestBobCLIServiceSuccess:

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_returns_recommendation_set(self, _):
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            result = await service.analyze(ctx)

        assert isinstance(result, RecommendationSet)

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_user_id_preserved(self, _):
        service = BobCLIService()
        ctx = make_work_context(user_id="specific-user-abc", active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            result = await service.analyze(ctx)

        assert result.user_id == "specific-user-abc"

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_model_version_is_bob_cli_v1(self, _):
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            result = await service.analyze(ctx)

        assert result.model_version == "bob-cli-v1"

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_recommendations_parsed_correctly(self, _):
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            result = await service.analyze(ctx)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert isinstance(rec, Recommendation)
        assert rec.priority == 1
        assert rec.category == "email"
        assert rec.source == "outlook"

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_metadata_contains_request_id(self, _):
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            result = await service.analyze(ctx)

        assert "request_id" in result.metadata
        assert result.metadata["request_id"] != ""

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_metadata_contains_active_sources(self, _):
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook", "slack"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            result = await service.analyze(ctx)

        assert set(result.metadata["active_sources"]) == {"outlook", "slack"}


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestBobCLIServiceTimeout:

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raises_bob_timeout_error_on_timeout(self, _):
        service = BobCLIService(timeout=0.001)
        ctx = make_work_context(active_source_names=["outlook"])

        async def slow_process(*_args, **_kwargs):
            await asyncio.sleep(10)
            return b"", b""

        with patch.object(BobCLIService, "_run_process", new=slow_process):
            with pytest.raises(BobTimeoutError) as exc_info:
                await service.analyze(ctx)

        assert "timed out" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Non-zero exit code
# ---------------------------------------------------------------------------

class TestBobCLIServiceExitCode:

    async def test_raises_bob_service_error_on_nonzero_exit(self):
        """_run_process raises BobServiceError when returncode != 0."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"auth error"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(BobServiceError) as exc_info:
                await BobCLIService._run_process(["bob"], "prompt")

        assert "return code 1" in exc_info.value.message

    async def test_exit_code_error_includes_stderr(self):
        """BobServiceError message includes stderr text when present."""
        mock_proc = MagicMock()
        mock_proc.returncode = 2
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: not authenticated"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(BobServiceError) as exc_info:
                await BobCLIService._run_process(["bob"], "prompt")

        assert "not authenticated" in exc_info.value.message

    async def test_zero_exit_returns_bytes(self):
        """_run_process returns (stdout, stderr) bytes on returncode == 0."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"stdout", b"stderr"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            stdout, stderr = await BobCLIService._run_process(["bob"], "prompt")

        assert stdout == b"stdout"
        assert stderr == b"stderr"


# ---------------------------------------------------------------------------
# Error result event
# ---------------------------------------------------------------------------

class TestBobCLIServiceErrorResult:

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raises_bob_service_error_on_result_error_status(self, _):
        """A stream-json result event with status=error raises BobServiceError."""
        service = BobCLIService()
        ctx = make_work_context()

        error_stream = (
            json.dumps({"type": "result", "status": "error", "stats": {}}) + "\n"
        ).encode("utf-8")

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(error_stream, b""))
        ):
            with pytest.raises(BobServiceError):
                await service.analyze(ctx)


# ---------------------------------------------------------------------------
# Response parsing errors
# ---------------------------------------------------------------------------

class TestBobCLIServiceResponseErrors:

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raises_bob_response_error_when_no_completion_event(self, _):
        """Stream-json with no attempt_completion tool_result raises BobResponseError."""
        service = BobCLIService()
        ctx = make_work_context()
        empty_stream = (
            json.dumps({"type": "result", "status": "success", "stats": {}}) + "\n"
        ).encode("utf-8")

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(empty_stream, b""))
        ):
            with pytest.raises(BobResponseError) as exc_info:
                await service.analyze(ctx)
        assert "attempt_completion" in exc_info.value.message

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raises_bob_response_error_on_non_json_output(self, _):
        """attempt_completion output that is not JSON raises BobResponseError."""
        service = BobCLIService()
        ctx = make_work_context()
        bad_output = "not valid json {{{"

        stream = (
            "\n".join([
                json.dumps({"type": "tool_use", "tool_name": "attempt_completion", "tool_id": "t1", "parameters": {}}),
                json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": bad_output}),
                json.dumps({"type": "result", "status": "success", "stats": {}}),
            ]) + "\n"
        ).encode("utf-8")

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stream, b""))
        ):
            with pytest.raises(BobResponseError) as exc_info:
                await service.analyze(ctx)
        assert "not valid JSON" in exc_info.value.message

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raises_bob_response_error_when_output_is_not_array(self, _):
        """attempt_completion output that is a JSON object, not array, raises BobResponseError."""
        service = BobCLIService()
        ctx = make_work_context()
        non_array = json.dumps({"priority": 1})

        stream = (
            "\n".join([
                json.dumps({"type": "tool_use", "tool_name": "attempt_completion", "tool_id": "t1", "parameters": {}}),
                json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": non_array}),
                json.dumps({"type": "result", "status": "success", "stats": {}}),
            ]) + "\n"
        ).encode("utf-8")

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stream, b""))
        ):
            with pytest.raises(BobResponseError) as exc_info:
                await service.analyze(ctx)
        assert "array" in exc_info.value.message.lower()

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raises_bob_response_error_on_malformed_recommendation(self, _):
        """A recommendation item missing required fields raises BobResponseError."""
        service = BobCLIService()
        ctx = make_work_context()
        bad_items = json.dumps([{"priority": 1}])  # missing category, title, description, source

        stream = (
            "\n".join([
                json.dumps({"type": "tool_use", "tool_name": "attempt_completion", "tool_id": "t1", "parameters": {}}),
                json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": bad_items}),
                json.dumps({"type": "result", "status": "success", "stats": {}}),
            ]) + "\n"
        ).encode("utf-8")

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stream, b""))
        ):
            with pytest.raises(BobResponseError) as exc_info:
                await service.analyze(ctx)
        assert "recommendations[0]" in exc_info.value.message


# ---------------------------------------------------------------------------
# Markdown fence stripping
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Debug logging of raw Bob output
# ---------------------------------------------------------------------------

class TestBobCLIServiceDebugLogging:

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raw_output_logged_at_debug(self, _, caplog):
        """Raw Bob output is logged at DEBUG level before parsing."""
        import logging as _logging
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            with caplog.at_level(_logging.DEBUG, logger="app.bob.cli_service"):
                await service.analyze(ctx)

        debug_messages = [r.getMessage() for r in caplog.records if r.levelno == _logging.DEBUG]
        assert any("raw Bob output" in msg for msg in debug_messages)

    @patch("shutil.which", return_value="/usr/local/bin/bob")
    async def test_raw_output_not_logged_at_info(self, _, caplog):
        """Raw Bob output must NOT appear at INFO level."""
        import logging as _logging
        service = BobCLIService()
        ctx = make_work_context(active_source_names=["outlook"])
        stdout = make_stream_json(make_valid_recommendation_list())

        with patch.object(
            BobCLIService, "_run_process", new=AsyncMock(return_value=(stdout, b""))
        ):
            with caplog.at_level(_logging.INFO, logger="app.bob.cli_service"):
                await service.analyze(ctx)

        info_messages = [r.getMessage() for r in caplog.records if r.levelno == _logging.INFO]
        assert not any("raw Bob output" in msg for msg in info_messages)


class TestParseRecommendationsMarkdownFences:

    def test_strips_json_markdown_fence(self):
        """Output wrapped in ```json ... ``` is parsed correctly."""
        items = make_valid_recommendation_list()
        fenced = f"```json\n{json.dumps(items)}\n```"
        result = _parse_recommendations(fenced, "req-test")
        assert len(result) == 1
        assert result[0].source == "outlook"

    def test_strips_plain_markdown_fence(self):
        """Output wrapped in ``` ... ``` (no language tag) is parsed correctly."""
        items = make_valid_recommendation_list()
        fenced = f"```\n{json.dumps(items)}\n```"
        result = _parse_recommendations(fenced, "req-test")
        assert len(result) == 1

    def test_plain_json_array_no_fences(self):
        """Plain JSON array without fences is parsed correctly."""
        items = make_valid_recommendation_list()
        result = _parse_recommendations(json.dumps(items), "req-test")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _local_timezone_name and _build_prompt timezone behaviour
# ---------------------------------------------------------------------------

class TestLocalTimezoneName:

    def test_returns_a_non_empty_string(self):
        """_local_timezone_name() always returns a non-empty string."""
        name = _local_timezone_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_falls_back_to_utc_on_exception(self, monkeypatch):
        """If datetime.now().astimezone() raises, returns 'UTC'."""
        import app.bob.cli_service as _module
        original = _module.datetime

        class _BrokenDatetime:
            @staticmethod
            def now(*_a, **_kw):
                raise OSError("no tz info")

        monkeypatch.setattr(_module, "datetime", _BrokenDatetime)
        result = _local_timezone_name()
        monkeypatch.setattr(_module, "datetime", original)
        assert result == "UTC"


class TestBuildPromptTimezone:

    def test_user_timezone_in_context_json(self, monkeypatch):
        """_build_prompt() embeds user_timezone derived from _local_timezone_name()."""
        import app.bob.cli_service as _module
        monkeypatch.setattr(_module, "_local_timezone_name", lambda: "IST")
        ctx = make_work_context()
        prompt = _build_prompt(ctx)
        assert '"user_timezone": "IST"' in prompt

    def test_user_timezone_never_uses_start_timezone_field(self, monkeypatch):
        """user_timezone comes from the OS, not from calendar event start_timezone."""
        import app.bob.cli_service as _module
        monkeypatch.setattr(_module, "_local_timezone_name", lambda: "PST")

        # Provide a calendar event whose start_timezone says something different.
        from app.connectors.models import ConnectorResult
        result = ConnectorResult.success(
            source="outlook",
            data={
                "calendar_events": [
                    {
                        "id": "e1",
                        "subject": "Stand-up",
                        "start": "2026-07-21T16:00:00.000Z",
                        "end": "2026-07-21T16:30:00.000Z",
                        "start_timezone": "India Standard Time",  # should be ignored
                    }
                ],
                "emails": [],
                "user": None,
            },
        )
        from app.context_builder.models import WorkContext
        ctx = WorkContext.from_connector_results(
            user_id="u1", results=[result]
        )
        prompt = _build_prompt(ctx)
        # OS timezone (PST) must appear, not the event's start_timezone
        assert '"user_timezone": "PST"' in prompt
        assert "India Standard Time" not in prompt.split('"user_timezone"')[1][:50]

    def test_prompt_contains_utc_conversion_instruction(self, monkeypatch):
        """Prompt tells Bob to convert UTC times to user_timezone before displaying."""
        import app.bob.cli_service as _module
        monkeypatch.setattr(_module, "_local_timezone_name", lambda: "IST")
        ctx = make_work_context()
        prompt = _build_prompt(ctx)
        assert "convert it from UTC" in prompt
        assert "user's local timezone" in prompt
