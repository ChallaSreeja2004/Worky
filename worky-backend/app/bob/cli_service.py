"""
app/bob/cli_service.py
=======================
BobCLIService — production BobService implementation that invokes Bob Shell.

HOW IT WORKS
------------
Bob Shell is invoked as a subprocess.  The WorkContext is serialised into a
structured prompt and written to the process's stdin.  Bob is started with
``--output-format stream-json`` so every output event is a newline-delimited
JSON object.  The parser scans the stream for the ``tool_result`` event whose
``tool_name`` is ``attempt_completion`` — that event's ``output`` field is
Bob's final answer, which is then parsed as a JSON array of Recommendation
objects.

REAL STREAM-JSON EVENT TYPES (observed)
----------------------------------------
  {"type":"init", ...}
  {"type":"message", "role":"user"|"assistant", "content":"...", "delta":true}
  {"type":"tool_use", "tool_name":"attempt_completion", "parameters":{"result":"..."}}
  {"type":"tool_result", "tool_id":"...", "status":"success", "output":"..."}  ← answer
  {"type":"result", "status":"success"|"error", "stats":{...}}                 ← final

The ``tool_result`` event with ``status == "success"`` that corresponds to the
``attempt_completion`` tool call contains Bob's clean final text in ``output``.
The ``result`` event signals process completion and carries cost/token stats.

PROMPT DESIGN
-------------
The prompt asks Bob to return a JSON array and nothing else.  Bob wraps its
response in markdown fences anyway (observed behaviour) — the parser strips
those automatically.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.bob.models
  • app.bob.service   (BobService ABC and exception hierarchy only)
  • app.bob.settings
  • app.context_builder.models

It must NOT import from:
  • app.connectors.*
  • app.auth
  • app.config
  • app.recommendations
  • fastapi
  • httpx
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

from app.bob.models import Recommendation, RecommendationSet
from app.bob.service import (
    BobConfigError,
    BobResponseError,
    BobService,
    BobServiceError,
    BobTimeoutError,
)
from app.context_builder.models import WorkContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a productivity assistant for an IBM employee.

Below is a JSON object describing the user's current work context across \
their enterprise tools (Outlook, GitHub, Jira, Slack, etc.).

IMPORTANT — TIMEZONE NOTE:
All calendar event start/end times in the context are in UTC (ISO 8601 with \
"Z" suffix, e.g. "2026-07-21T16:00:00.000Z"). The "user_timezone" field \
names the user's local timezone (e.g. "IST", "EST", "PST"). When you mention \
a meeting time in a recommendation title or description, convert it from UTC \
to the user's local timezone before writing the time. For example, if \
user_timezone is "IST" (UTC+5:30) and a meeting starts at \
"2026-07-21T16:00:00.000Z", write "9:30 PM IST" — never write the raw UTC \
time. If "user_timezone" is "UTC", write the time as-is with "UTC" appended.

Analyse this context and return ONLY a JSON array of prioritised action \
recommendations. Return nothing else — no prose, no markdown fences, \
no explanation.

Each item in the array must have exactly these fields:
  "priority"    — integer starting at 1 (1 = most urgent)
  "category"    — one of: "email", "meeting", "message", "task", "general"
  "title"       — short action-oriented headline, max 80 characters
  "description" — 1-2 sentences explaining why this is urgent
  "action_url"  — deep-link URL to the source item, or empty string ""
  "source"      — connector name: "outlook", "slack", "github", "jira", etc.

Return between 1 and 10 recommendations when sufficient work context exists.
If there are no actionable tasks or the work context contains no usable data, return an empty JSON array [].
If a source has no data or failed, skip it.

Work context:
{context_json}"""


def _local_timezone_name() -> str:
    """
    Return the abbreviated name of the system's local timezone.

    Examples: "IST", "EST", "PST", "UTC".

    Uses datetime.now().astimezone() which reads the OS timezone — correct for
    a desktop app where the backend runs on the user's own machine.  Falls back
    to "UTC" only when the platform cannot determine a timezone name.
    """
    try:
        name = datetime.now(timezone.utc).astimezone().tzname()
        return name or "UTC"
    except Exception:  # noqa: BLE001
        return "UTC"


def _build_prompt(work_context: WorkContext) -> str:
    """Serialise the WorkContext into a Bob Shell prompt string."""
    # Derive the user's display timezone from the OS — the backend runs as a
    # desktop process on the user's machine, so the system timezone is the
    # user's local timezone.  This is more reliable than reading start_timezone
    # from Graph events, which always reflects the Prefer header value ("UTC")
    # rather than the user's geographic timezone.
    user_timezone = _local_timezone_name()

    context_payload: dict[str, Any] = {
        "user_id": work_context.user_id,
        "assembled_at": work_context.assembled_at.isoformat(),
        "active_sources": work_context.active_sources,
        "sources": work_context.sources,
        "connector_summaries": [
            {
                "source": s.source,
                "status": s.status.value,
                "error_count": s.error_count,
            }
            for s in work_context.connector_summaries
        ],
        "errors": work_context.errors,
        # Timezone hint for Bob: all calendar datetimes are UTC; this field
        # names the user's local timezone (from the OS) so Bob can convert
        # meeting times from UTC to the user's local time for display.
        "user_timezone": user_timezone,
    }
    context_json = json.dumps(context_payload, default=str, indent=2)
    return _PROMPT_TEMPLATE.format(context_json=context_json)


# ---------------------------------------------------------------------------
# stream-json parser
# ---------------------------------------------------------------------------

def _extract_completion_output(stream_lines: list[str], request_id: str) -> str:
    """
    Scan stream-json lines and return the ``output`` of the
    ``attempt_completion`` tool_result event.

    Bob's stream-json format emits one JSON object per line.  The final
    answer always appears in the event:
      {"type":"tool_result", "status":"success", "output":"<answer>"}
    where the preceding tool_use had ``"tool_name": "attempt_completion"``.

    Raises
    ------
    BobResponseError
        If no completion output is found, or the ``result`` event carries
        ``"status": "error"``.
    """
    completion_tool_ids: set[str] = set()

    for raw_line in stream_lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON lines (e.g., stderr mixed in) are ignored.
            continue

        event_type = event.get("type")

        # Track which tool_ids belong to attempt_completion calls.
        if event_type == "tool_use" and event.get("tool_name") == "attempt_completion":
            tool_id = event.get("tool_id")
            if tool_id:
                completion_tool_ids.add(tool_id)

        # The tool_result for attempt_completion contains the final answer.
        if event_type == "tool_result" and event.get("tool_id") in completion_tool_ids:
            if event.get("status") != "success":
                raise BobResponseError(
                    f"Bob attempt_completion returned non-success status "
                    f"(request_id={request_id})."
                )
            output = event.get("output", "")
            if not isinstance(output, str):
                raise BobResponseError(
                    f"Bob attempt_completion output is not a string "
                    f"(request_id={request_id})."
                )
            return output

        # Top-level result event with error status.
        if event_type == "result" and event.get("status") == "error":
            raise BobServiceError(
                f"Bob Shell exited with error status "
                f"(request_id={request_id})."
            )

    raise BobResponseError(
        f"Bob stream-json contained no attempt_completion tool_result "
        f"(request_id={request_id})."
    )


def _parse_recommendations(raw_output: str, request_id: str) -> list[Recommendation]:
    """
    Parse Bob's raw text output into a list of Recommendation objects.

    Strips markdown fences if present (Bob wraps JSON in ```json ... ```
    despite being told not to — observed in live testing).

    Raises
    ------
    BobResponseError
        If the text is not a valid JSON array or any item fails Pydantic
        validation.
    """
    text = raw_output.strip()

    # Strip markdown code fences that Bob adds regardless of instructions.
    # Handles both ```json\n...\n``` and ```\n...\n``` (no language tag).
    if text.startswith("```"):
        # Remove the opening fence line (```json or ``` or ```python etc.)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove the closing ``` fence (last line)
        last_fence = text.rfind("```")
        if last_fence != -1:
            text = text[:last_fence]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BobResponseError(
            f"Bob output is not valid JSON (request_id={request_id}): {exc}"
        ) from exc

    if not isinstance(parsed, list):
        raise BobResponseError(
            f"Bob output must be a JSON array, "
            f"got {type(parsed).__name__!r} (request_id={request_id})."
        )

    recommendations: list[Recommendation] = []
    for i, item in enumerate(parsed):
        try:
            recommendations.append(Recommendation.model_validate(item))
        except Exception as exc:
            raise BobResponseError(
                f"Bob recommendations[{i}] failed validation "
                f"(request_id={request_id}): {exc}"
            ) from exc

    return recommendations


# ---------------------------------------------------------------------------
# BobCLIService
# ---------------------------------------------------------------------------

class BobCLIService(BobService):
    """
    Production BobService that invokes Bob Shell as a subprocess.

    Sends the WorkContext as a structured prompt via stdin, reads the
    stream-json output, extracts the attempt_completion result, and
    parses it into a RecommendationSet.

    Parameters
    ----------
    bob_executable : str
        Path or name of the bob CLI command.  Defaults to ``"bob"``,
        which resolves via PATH.
    chat_mode : str
        Bob chat mode.  ``"ask"`` is correct for read-only reasoning.
    timeout : float
        Total seconds to wait for Bob to respond before raising
        BobTimeoutError.  Bob generation can take 15–30 s for complex
        contexts.  Default: 120 s.

    Usage (via DI in app/bob/dependencies.py):
    ::

        from app.bob.cli_service import BobCLIService
        from app.bob.settings import get_bob_settings

        @lru_cache
        def _get_shared_bob_service() -> BobCLIService:
            s = get_bob_settings()
            return BobCLIService(
                bob_executable=s.bob_executable,
                chat_mode=s.bob_chat_mode,
                timeout=s.bob_timeout_seconds,
            )
    """

    _MODEL_VERSION: str = "bob-cli-v1"

    def __init__(
        self,
        bob_executable: str = "bob",
        chat_mode: str = "ask",
        timeout: float = 120.0,
    ) -> None:
        resolved = shutil.which(bob_executable)
        if resolved is None:
            raise BobConfigError(
                f"Bob Shell executable not found: {bob_executable!r}. "
                "Ensure Bob Shell is installed and available on PATH."
            )
        self._bob_executable = resolved
        self._chat_mode = chat_mode
        self._timeout = timeout

    async def analyze(self, work_context: WorkContext) -> RecommendationSet:
        """
        Invoke Bob Shell with the WorkContext and return a RecommendationSet.

        Raises
        ------
        BobTimeoutError
            If Bob does not complete within ``timeout`` seconds.
        BobServiceError
            If Bob exits with a non-zero return code or reports an error.
        BobResponseError
            If the stream-json output cannot be parsed into recommendations.
        BobConfigError
            If the bob executable is not found (raised at construction time,
            not here — but documented for completeness).
        """
        request_id = str(uuid.uuid4())
        prompt = _build_prompt(work_context)

        logger.info(
            "BobCLIService: invoking Bob Shell — user_id=%s request_id=%s "
            "active_sources=%s",
            work_context.user_id,
            request_id,
            work_context.active_sources,
        )

        cmd = [
            self._bob_executable,
            "--output-format", "stream-json",
            "--hide-intermediary-output",
            "--chat-mode", self._chat_mode,
            "--approval-mode", "yolo",
        ]

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                self._run_process(cmd, prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise BobTimeoutError(
                f"Bob Shell timed out after {self._timeout}s "
                f"(request_id={request_id})."
            ) from exc

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # Log stderr at DEBUG — it contains Bob's operational output.
        if stderr.strip():
            logger.debug(
                "BobCLIService: stderr — request_id=%s\n%s",
                request_id,
                stderr,
            )

        stream_lines = stdout.splitlines()

        # Check for non-zero exit via the final "result" event before
        # inspecting the process return code, since Bob always emits
        # "result" with status on clean completion.
        raw_output = _extract_completion_output(stream_lines, request_id)

        logger.debug(
            "BobCLIService: raw Bob output (request_id=%s):\n%s",
            request_id,
            raw_output,
        )

        recommendations = _parse_recommendations(raw_output, request_id)

        recommendation_set = RecommendationSet(
            user_id=work_context.user_id,
            recommendations=recommendations,
            model_version=self._MODEL_VERSION,
            metadata={
                "request_id": request_id,
                "active_sources": work_context.active_sources,
            },
        )

        logger.info(
            "BobCLIService: analysis complete — user_id=%s request_id=%s "
            "recommendations=%d",
            work_context.user_id,
            request_id,
            len(recommendations),
        )

        return recommendation_set

    @staticmethod
    async def _run_process(cmd: list[str], stdin_text: str) -> tuple[bytes, bytes]:
        """
        Run *cmd* as an async subprocess, write *stdin_text* to its stdin,
        and return (stdout_bytes, stderr_bytes) when it exits.

        Raises
        ------
        BobServiceError
            If the process exits with a non-zero return code.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate(
            input=stdin_text.encode("utf-8")
        )
        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            detail = f": {stderr_text}" if stderr_text else ""
            raise BobServiceError(
                f"Bob Shell exited with return code {proc.returncode}{detail}"
            )
        return stdout_bytes, stderr_bytes
