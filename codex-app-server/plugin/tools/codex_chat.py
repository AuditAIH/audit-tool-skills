"""Codex chat tool: drives a codex-app-server HTTP service.

Sends ``POST /api/messages`` to a codex-app-server endpoint and streams the
codex agent's reply back to the Dify user.  The codex-app-server wraps the
codex ``app-server`` JSON-RPC protocol; every app-server notification is
forwarded as one SSE ``data:`` frame carrying a ``method`` field, and the
server appends a synthetic ``done`` summary frame when the turn finishes.

Rendering follows the official OpenAI plugin's convention
(``models/llm/stream.py``): reasoning summaries and process items (commands,
file changes, tool calls) are wrapped in a ``<think>...</think>`` section
that Dify renders as a collapsible "thinking" block, while agent messages
render as normal answer text outside of it.  ``<think>`` is opened lazily on
the first reasoning/process piece and closed right before answer text, and
the tag is balanced when the stream ends.

The current app-server spec streams each item as a complete ``item/started``
then ``item/completed`` notification (agent-message and reasoning deltas are
opted out by default), so every item is rendered from its authoritative final
state on ``item/completed``.
"""

import json
import logging
import time
from collections.abc import Generator, Iterator
from typing import Any

import httpx
from dify_plugin import Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

DEFAULT_SERVER_URL = "http://host.docker.internal:5040"

# No overall read timeout: codex runs can take minutes.  Only the connect
# phase is bounded so a dead endpoint fails fast.
HTTP_TIMEOUT = httpx.Timeout(timeout=None, connect=10.0)

# Terminate is best-effort cleanup when the user stops the stream.  The POST
# is sent while the SSE is still open (inside the GeneratorExit handler) so
# the server sees an active turn and turn/interrupt is delivered immediately;
# we only wait for confirmation, capped short so the node stops promptly and
# its execution duration is not inflated.  Even on timeout the interrupt has
# already been sent, so codex still stops.
TERMINATE_TIMEOUT = httpx.Timeout(timeout=5.0, connect=5.0)

# Method names carried by the synthetic frames produced by codex-app-server.
METHOD_DONE = "done"
METHOD_ERROR = "error"
# Tag attached to a non-SSE (JSON) response so the consumer can tell it apart
# from a streamed notification.
METHOD_JSON = "__json_response__"


def _build_headers(api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _messages_url(server_url: str) -> str:
    return f"{server_url.rstrip('/')}/api/messages"


def _build_payload(
    query: str,
    conversation_id: str,
    app_id: str,
    user_id: str,
    stream: bool,
) -> dict[str, Any]:
    return {
        "query": query,
        "conversation_id": conversation_id,
        "app_id": app_id,
        "user_id": user_id,
        "stream": stream,
    }


def _iter_sse_events(response: "httpx.Response") -> Iterator[dict[str, Any]]:
    """Yield each decoded ``data:`` JSON frame from an open SSE response.

    SSE comment lines (starting with ``:``) and blank lines are skipped;
    non-JSON frames are logged and skipped.
    """
    for raw_line in response.iter_lines():
        if raw_line is None:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            logger.warning("skip non-JSON frame: %s", line[:200])
            continue
        if isinstance(event, dict):
            yield event


def terminate_turn(
    server_url: str,
    api_key: str,
    conversation_id: str,
    app_id: str,
    user_id: str,
) -> None:
    """Best-effort: ask codex-app-server to abort the active turn.

    Sends an empty-query ``POST /api/messages`` (the server README's "terminate"
    contract).  The server replies ``terminated`` / ``no_active_turn`` /
    ``no_conversation`` -- any outcome is acceptable, so all errors are swallowed.
    """
    if not conversation_id:
        logger.warning(
            "codex-app-server terminate skipped: no conversation_id "
            "(new conversation aborted before its id was known)"
        )
        return
    url = _messages_url(server_url)
    headers = _build_headers(api_key)
    payload: dict[str, Any] = {
        "query": "",
        "conversation_id": conversation_id,
        "user_id": user_id,
    }
    if app_id:
        payload["app_id"] = app_id
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=TERMINATE_TIMEOUT)
        logger.info(
            "codex-app-server terminate conversation=%s status_code=%s body=%s",
            conversation_id, resp.status_code, resp.text[:200],
        )
    except Exception as e:  # best-effort: never raise from cleanup
        logger.warning("codex-app-server terminate failed (best-effort): %s", e)


def call_aggregate(
    server_url: str,
    api_key: str,
    query: str,
    conversation_id: str,
    app_id: str,
    user_id: str,
) -> dict[str, Any]:
    """POST /api/messages without stream and return the parsed JSON response."""
    url = _messages_url(server_url)
    headers = _build_headers(api_key)
    payload = _build_payload(query, conversation_id, app_id, user_id, stream=False)
    response = httpx.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"codex-app-server returned HTTP {response.status_code}: {response.text or '(empty)'}"
        )
    return response.json()


class ThinkStreamFormatter:
    """Render codex app-server item lifecycle events as a streamed markdown doc.

    The current app-server spec streams each item as a complete ``item/started``
    then ``item/completed`` notification (agent-message and reasoning deltas are
    opted out by default), so every item is rendered from its authoritative
    final state on ``item/completed``.  Command output, however, IS streamed
    live via ``item/commandExecution/outputDelta``; we open a bash code fence on
    the first delta and close it when the command completes, so long-running
    commands surface their output in real time.  Reasoning summaries
    and process items (commands, file changes, tool calls, web searches) are
    wrapped in a ``<think>...</think>`` section that Dify renders as a
    collapsible "thinking" block; agent messages render as normal answer text
    outside of it.
    """

    def __init__(self) -> None:
        self._thinking = False
        self._answered = False
        self._last_plan_snapshot: list[tuple[str, str]] | None = None
        # itemId -> command text, captured from item/started so the live
        # output fence can show the ``$ command`` prompt line.
        self._cmd_command: dict[str, str] = {}
        # itemId of the command whose bash fence is currently open (None when
        # no command is streaming).
        self._open_cmd: str | None = None

    def _open(self) -> str:
        if not self._thinking:
            self._thinking = True
            # The frontend's think preprocessor eats all whitespace after
            # ``<think>``, so the first content line would land inside the
            # markdown HTML block and render as raw text (breaking lists and
            # code fences).  An empty comment followed by a blank line closes
            # the HTML block; the sanitizer strips the comment itself.
            return "<think>\n<!-- -->\n\n"
        return ""

    def _close(self) -> str:
        if self._thinking:
            self._thinking = False
            return "\n</think>\n\n"
        return ""

    def _think_prefix(self) -> str:
        """Open the think block if needed, or return a newline separator so a
        process item / plan never runs into preceding think-block text."""
        prefix = self._open()
        if not prefix and self._thinking:
            return "\n"
        return prefix

    def _close_open_command(self) -> str:
        """Defensively close an open command-output code fence."""
        if self._open_cmd is not None:
            self._open_cmd = None
            return "\n```\n\n"
        return ""

    # -- item lifecycle ---------------------------------------------------

    def format_started_item(self, item: dict[str, Any]) -> str | None:
        # Remember the command text so the live output fence can print the
        # ``$ command`` prompt line when the first output delta arrives.
        if item.get("type") == "commandExecution":
            item_id = str(item.get("id") or "")
            command = str(item.get("command") or "").strip()
            if item_id and command:
                self._cmd_command[item_id] = command
        return None

    def command_output_delta(self, item_id: str, delta: str) -> str | None:
        """Stream live command output into a bash code fence in the think block."""
        if not delta or not item_id:
            return None
        if item_id != self._open_cmd:
            command = self._cmd_command.get(item_id, "")
            parts: list[str] = [self._open(), "```bash\n"]
            if command:
                parts.append(f"$ {command}\n")
            parts.append(delta)
            self._open_cmd = item_id
            return "".join(parts)
        return delta

    def format_completed_item(self, item: dict[str, Any]) -> str | None:
        """Render an ``item/completed`` item from its authoritative final state."""
        item_type = item.get("type")
        if item_type == "commandExecution":
            return self._complete_command(item)
        # Defensively close any still-open command fence before rendering
        # non-command content (normally a command completes first).
        pre = self._close_open_command()
        if item_type == "agentMessage":
            text = str(item.get("text") or "").strip()
            if not text:
                return pre or None
            self._answered = True
            return f"{pre}{self._close()}{text}\n\n"
        if item_type == "reasoning":
            text = _reasoning_text(item)
            if not text:
                return pre or None
            return f"{pre}{self._open()}{text}\n\n"
        body = _format_process_item(item)
        if not body:
            return pre or None
        return f"{pre}{self._think_prefix()}{body}\n\n"

    def _complete_command(self, item: dict[str, Any]) -> str | None:
        item_id = str(item.get("id") or "")
        status = str(item.get("status") or "").strip()
        exit_code = item.get("exitCode")
        self._cmd_command.pop(item_id, None)
        if item_id and item_id == self._open_cmd:
            # Output was streamed live: close the fence, appending a status
            # note for non-success exits (inside the fence).
            suffix = ""
            if status and status != "completed":
                note = f"# status={status}"
                if exit_code is not None:
                    note += f" exit_code={exit_code}"
                suffix = f"\n{note}"
            self._open_cmd = None
            return f"{suffix}\n```\n\n"
        # No live output: render the full block from the completed item.
        body = _format_process_item(item)
        if not body:
            return None
        return f"{self._think_prefix()}{body}\n\n"

    def format_plan(self, explanation: str | None, plan: list[Any]) -> str | None:
        """Render a ``turn/plan/updated`` snapshot as a task list."""
        snapshot: list[tuple[str, str]] = []
        lines: list[str] = []
        for entry in plan:
            if not isinstance(entry, dict):
                continue
            step = str(entry.get("step") or "").strip()
            if not step:
                continue
            status = str(entry.get("status") or "pending").strip()
            snapshot.append((step, status))
            mark = _plan_mark(status)
            lines.append(f"- [{mark}] {step}")
        if not lines or snapshot == self._last_plan_snapshot:
            return None
        self._last_plan_snapshot = snapshot
        pre = self._close_open_command()
        header = f"{explanation.strip()}\n\n" if explanation else ""
        return f"{pre}{self._think_prefix()}{header}{chr(10).join(lines)}\n\n"

    def format_event(self, event: dict[str, Any]) -> str | None:
        """Dispatch one app-server notification to the right renderer."""
        method = event.get("method") or ""
        if method == "item/started":
            item = event.get("item")
            if isinstance(item, dict):
                return self.format_started_item(item)
            return None
        if method == "item/completed":
            item = event.get("item")
            if isinstance(item, dict):
                return self.format_completed_item(item)
            return None
        if method == "item/commandExecution/outputDelta":
            return self.command_output_delta(
                str(event.get("itemId") or ""), str(event.get("delta") or "")
            )
        if method == "turn/plan/updated":
            plan = event.get("plan")
            if isinstance(plan, list):
                explanation = event.get("explanation")
                return self.format_plan(
                    str(explanation) if explanation is not None else None, plan
                )
            return None
        # turn/*, thread/* and other notifications carry no user-visible
        # content here; they are logged by the caller.
        return None

    def finalize(self) -> str | None:
        """Close any open command fence and balance an unclosed ``<think>``."""
        parts = [self._close_open_command(), self._close()]
        return "".join(p for p in parts if p) or None


def _reasoning_text(item: dict[str, Any]) -> str:
    """Extract readable text from a reasoning item.

    App-server reasoning items carry a ``summary`` list of strings (the
    streamed reasoning summaries).  Older items may use a ``text`` field.
    """
    summary = item.get("summary")
    if isinstance(summary, list):
        parts = [str(s).strip() for s in summary if str(s).strip()]
        text = "\n".join(parts)
    else:
        text = str(item.get("text") or "").strip()
    # codex emits shim reasoning whose whole text is "tool call"; drop it.
    if text.lower() == "tool call":
        return ""
    return text


def _plan_mark(status: str) -> str:
    s = status.lower()
    if s in ("completed", "done"):
        return "x"
    if s in ("inprogress", "in_progress", "active", "running"):
        return ">"
    return " "


def _format_process_item(item: dict[str, Any]) -> str | None:
    """Render one non-answer codex item with its own native fields only."""
    item_type = item.get("type")
    if item_type == "commandExecution":
        command = str(item.get("command") or "").strip()
        if not command:
            return None
        output = str(item.get("aggregatedOutput") or "").strip()
        if len(output) > 4000:
            output = output[:4000] + "\n... (truncated)"
        # One terminal-style block per command: the ``$`` prompt line first,
        # then its output, so input and result stay together.
        lines = [f"$ {command}"]
        if output:
            lines.append(output)
        status = str(item.get("status") or "").strip()
        if status and status != "completed":
            exit_code = item.get("exitCode")
            suffix = f"# status={status}"
            if exit_code is not None:
                suffix += f" exit_code={exit_code}"
            lines.append(suffix)
        body = "\n".join(lines)
        fence = "````" if "```" in body else "```"
        return f"{fence}bash\n{body}\n{fence}"
    if item_type == "fileChange":
        changes = item.get("changes") or []
        lines = []
        for change in changes:
            if not isinstance(change, dict) or not change.get("path"):
                continue
            kind = change.get("kind")
            if isinstance(kind, dict):
                kind = kind.get("type")
            lines.append(f"- {kind or 'change'} {change['path']}")
        return "\n".join(lines) or None
    if item_type == "mcpToolCall":
        server = str(item.get("server") or "").strip()
        tool_name = str(item.get("tool") or "").strip()
        if not tool_name:
            return None
        label = f"{server}/{tool_name}" if server else tool_name
        status = str(item.get("status") or "").strip()
        if status and status != "completed":
            label += f" (status={status})"
        return label
    if item_type == "dynamicToolCall":
        tool_name = str(item.get("tool") or "").strip()
        if not tool_name:
            return None
        label = tool_name
        status = str(item.get("status") or "").strip()
        if status and status != "completed":
            label += f" (status={status})"
        return label
    if item_type == "webSearch":
        search_query = str(item.get("query") or "").strip()
        return f"web_search: `{search_query}`" if search_query else None
    return None


class CodexChatTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        logger.info("codex-app-server chat tool_parameters: %s", tool_parameters)

        query = str(tool_parameters.get("query") or "").strip()
        conversation_id = str(tool_parameters.get("conversation_id") or "").strip()
        app_id = str(tool_parameters.get("app_id") or "").strip()
        user_id = str(tool_parameters.get("user_id") or "").strip()
        stream = tool_parameters.get("stream")
        if stream is None:
            stream = True
        stream = bool(stream)

        if not query:
            raise ValueError("query cannot be empty.")
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty.")
        if not app_id:
            raise ValueError("app_id cannot be empty.")
        if not user_id:
            raise ValueError("user_id cannot be empty.")

        credentials = getattr(getattr(self, "runtime", None), "credentials", None) or {}
        server_url = str(credentials.get("server_url") or DEFAULT_SERVER_URL).strip()
        api_key = str(credentials.get("api_key") or "").strip()
        if not server_url.startswith(("http://", "https://")):
            raise ValueError("server_url credential must start with http:// or https://.")

        logger.info(
            "codex-app-server request conversation=%s app=%s user=%s server=%s stream=%s",
            conversation_id, app_id, user_id, server_url, stream,
        )

        try:
            if not stream:
                yield from self._invoke_aggregate(
                    server_url, api_key, query, conversation_id, app_id, user_id
                )
                return
            yield from self._invoke_stream(
                server_url, api_key, query, conversation_id, app_id, user_id
            )
        except httpx.HTTPError as e:
            err_msg = f"HTTP error when calling codex-app-server: {e}"
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

    # -- non-streaming ----------------------------------------------------

    def _invoke_aggregate(
        self, server_url, api_key, query, conversation_id, app_id, user_id
    ) -> Generator[ToolInvokeMessage, None, None]:
        result = call_aggregate(server_url, api_key, query, conversation_id, app_id, user_id)
        status = str(result.get("status") or "").strip()
        error = str(result.get("error") or "").strip()
        message = str(result.get("message") or "").strip()
        logger.info(
            "codex-app-server aggregate conversation=%s status=%s",
            result.get("conversation_id"), status,
        )
        if status == "steered":
            yield self.create_text_message(
                "Message added to the running turn (steered). "
                "Its output will appear in the ongoing stream."
            )
            return
        if error:
            raise RuntimeError(f"codex-app-server error: {error}")
        if message:
            yield self.create_text_message(message)
        else:
            yield self.create_text_message("(codex returned an empty message)")

    # -- streaming --------------------------------------------------------

    def _invoke_stream(
        self, server_url, api_key, query, conversation_id, app_id, user_id
    ) -> Generator[ToolInvokeMessage, None, None]:
        started_at = time.monotonic()
        formatter = ThinkStreamFormatter()
        saw_done = False
        final_status: str | None = None
        final_error: str | None = None
        # True once the turn reached a terminal state (done/error frame or a
        # clean end of stream).  When the user stops the stream mid-turn this
        # stays False and we terminate the active codex turn on the way out.
        turn_finished = False
        terminated = False

        url = _messages_url(server_url)
        headers = _build_headers(api_key)
        payload = _build_payload(query, conversation_id, app_id, user_id, stream=True)

        try:
            with httpx.stream(
                "POST", url, json=payload, headers=headers, timeout=HTTP_TIMEOUT
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    response.read()
                    body = response.text or "(empty)"
                    raise RuntimeError(
                        f"codex-app-server returned HTTP {response.status_code}: {body}"
                    )
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    # Non-SSE JSON response (e.g. a steered turn): there is no
                    # streaming turn to abort, so nothing to terminate.
                    turn_finished = True
                    response.read()
                    try:
                        data = response.json()
                    except ValueError as e:
                        raise RuntimeError(
                            f"codex-app-server returned non-JSON, non-SSE body: "
                            f"{response.text[:300]}"
                        ) from e
                    if isinstance(data, dict):
                        data.setdefault("method", METHOD_JSON)
                        yield from self._handle_json_response(data)
                    return

                try:
                    for event in _iter_sse_events(response):
                        method = event.get("method") or ""
                        if method:
                            logger.info(
                                "codex-app-server event method=%s elapsed=%.1fs",
                                method, time.monotonic() - started_at,
                            )

                        if method == METHOD_DONE:
                            saw_done = True
                            turn_finished = True
                            final_status = str(event.get("status") or "").strip()
                            final_error = str(event.get("error") or "").strip()
                            logger.info(
                                "codex-app-server done conversation=%s thread=%s turn=%s status=%s",
                                event.get("conversation_id"), event.get("thread_id"),
                                event.get("turn_id"), final_status,
                            )
                            tail = formatter.finalize()
                            if tail:
                                yield self.create_text_message(tail)
                            continue

                        if method == METHOD_ERROR:
                            turn_finished = True
                            err_msg = str(event.get("error") or "unknown error from codex-app-server")
                            logger.error(err_msg)
                            tail = formatter.finalize()
                            if tail:
                                yield self.create_text_message(tail)
                            raise RuntimeError(err_msg)

                        chunk = formatter.format_event(event)
                        if chunk:
                            yield self.create_text_message(chunk)

                    # Stream ended normally.
                    turn_finished = True
                    tail = formatter.finalize()
                    if tail:
                        yield self.create_text_message(tail)
                    if final_error:
                        raise RuntimeError(f"codex-app-server turn failed: {final_error}")
                    if final_status == "failed":
                        raise RuntimeError("codex-app-server turn ended with status 'failed'.")
                    if not saw_done:
                        logger.warning("codex-app-server stream ended without a done frame")
                except GeneratorExit:
                    # The user stopped the stream in Dify.  The SSE connection
                    # to codex-app-server is still open here (the ``with`` has
                    # not exited yet), so the server still sees an active turn
                    # and the terminate request can actually interrupt it.
                    if not turn_finished:
                        logger.info(
                            "codex-app-server stream aborted by user; terminating turn conversation=%s",
                            conversation_id,
                        )
                        terminate_turn(server_url, api_key, conversation_id, app_id, user_id)
                        terminated = True
                    raise
        finally:
            # Any other non-clean exit (timeout, broken pipe, ...) where the
            # turn never finished: best-effort terminate.  The SSE is already
            # closed by now, so the server may report no_active_turn.
            if not turn_finished and not terminated:
                terminate_turn(server_url, api_key, conversation_id, app_id, user_id)

    def _handle_json_response(
        self, event: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        status = str(event.get("status") or "").strip()
        if status == "steered":
            yield self.create_text_message(
                "Message added to the running turn (steered). "
                "Its output will appear in the ongoing stream."
            )
            return
        error = str(event.get("error") or "").strip()
        if error:
            raise RuntimeError(f"codex-app-server error: {error}")
        message = str(event.get("message") or "").strip()
        if message:
            yield self.create_text_message(message)
        else:
            yield self.create_text_message("(codex returned an empty message)")
