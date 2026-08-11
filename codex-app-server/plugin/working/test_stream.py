"""Unit test for the streaming pipeline with a mocked HTTP transport.

Usage: .venv/bin/python working/test_stream.py
"""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from dify_plugin.entities.tool import ToolInvokeMessage  # noqa: E402
from tools import codex_chat as cc  # noqa: E402


class FakeResponse:
    def __init__(self, lines, status_code=200, content_type="text/event-stream"):
        self._lines = lines
        self.status_code = status_code
        self.headers = httpx.Headers({"content-type": content_type})
        self._text = "".join(l + "\n" for l in lines)

    def iter_lines(self):
        for line in self._lines:
            yield line

    def read(self):
        return self._text

    @property
    def text(self):
        return self._text

    def json(self):
        return json.loads(self._text.strip())


@contextmanager
def fake_stream(resp):
    yield resp


def make_tool():
    tool = cc.CodexChatTool.__new__(cc.CodexChatTool)
    tool.runtime = SimpleNamespace(credentials={"server_url": "http://test:5040", "api_key": ""})
    tool.response_type = ToolInvokeMessage
    return tool


def sse(events):
    lines = []
    for ev in events:
        lines.append(f"data: {json.dumps(ev)}")
        lines.append("")  # blank line between frames
    return lines


def test_streaming_turn():
    events = [
        {"method": "turn/started", "turn": {"id": "t1"}},
        {"method": "item/reasoning/summaryTextDelta", "delta": "Thinking..."},
        {"method": "item/agentMessage/delta", "delta": "Hello "},
        {"method": "item/agentMessage/delta", "delta": "world!"},
        {"method": "turn/completed", "turn": {"id": "t1", "status": "completed"}},
        {"method": "done", "status": "completed", "conversation_id": "c1",
         "thread_id": "th1", "turn_id": "t1", "message": "Hello world!", "error": ""},
    ]
    resp = FakeResponse(sse(events))
    with patch.object(httpx, "stream", return_value=fake_stream(resp)):
        tool = make_tool()
        chunks = [m.message.text for m in tool._invoke({
            "query": "hi", "conversation_id": "c1", "app_id": "a", "user_id": "u", "stream": True
        })]
    out = "".join(chunks)
    print("=== test_streaming_turn ===")
    print(repr(out))
    assert "<think>" in out and "</think>" in out
    assert "Thinking..." in out
    assert "Hello world!" in out
    assert out.index("</think>") < out.index("Hello")
    print("PASS\n")


def test_steered_response():
    # Server returns JSON (not SSE) when the input is steered into a running turn.
    body = {"conversation_id": "c1", "thread_id": "th1", "turn_id": "t1",
            "status": "steered", "message": ""}
    resp = FakeResponse([json.dumps(body)], content_type="application/json")
    with patch.object(httpx, "stream", return_value=fake_stream(resp)):
        tool = make_tool()
        chunks = [m.message.text for m in tool._invoke({
            "query": "more", "conversation_id": "c1", "app_id": "a", "user_id": "u", "stream": True
        })]
    out = "".join(chunks)
    print("=== test_steered_response ===")
    print(repr(out))
    assert "steered" in out.lower()
    print("PASS\n")


def test_error_frame():
    events = [
        {"method": "error", "error": "boom"},
    ]
    resp = FakeResponse(sse(events))
    with patch.object(httpx, "stream", return_value=fake_stream(resp)):
        tool = make_tool()
        try:
            list(tool._invoke({
                "query": "hi", "conversation_id": "c1", "app_id": "a", "user_id": "u", "stream": True
            }))
            assert False, "should have raised"
        except RuntimeError as e:
            print("=== test_error_frame ===")
            print(f"raised: {e}")
            assert "boom" in str(e)
            print("PASS\n")


def test_failed_turn():
    events = [
        {"method": "item/agentMessage/delta", "delta": "partial"},
        {"method": "turn/completed", "turn": {"id": "t1", "status": "failed",
               "error": {"message": "context exceeded"}}},
        {"method": "done", "status": "failed", "error": "context exceeded",
         "conversation_id": "c1"},
    ]
    resp = FakeResponse(sse(events))
    with patch.object(httpx, "stream", return_value=fake_stream(resp)):
        tool = make_tool()
        try:
            list(tool._invoke({
                "query": "hi", "conversation_id": "c1", "app_id": "a", "user_id": "u", "stream": True
            }))
            assert False, "should have raised for failed turn"
        except RuntimeError as e:
            print("=== test_failed_turn ===")
            print(f"raised: {e}")
            assert "failed" in str(e).lower() or "context" in str(e).lower()
            print("PASS\n")


def test_non_streaming():
    body = {"conversation_id": "c1", "thread_id": "th1", "turn_id": "t1",
            "message": "Full reply here.", "status": "completed"}
    with patch.object(httpx, "post", return_value=FakeResponse(
            [json.dumps(body)], content_type="application/json")):
        tool = make_tool()
        chunks = [m.message.text for m in tool._invoke({
            "query": "hi", "conversation_id": "c1", "app_id": "a", "user_id": "u", "stream": False
        })]
    out = "".join(chunks)
    print("=== test_non_streaming ===")
    print(repr(out))
    assert "Full reply here." in out
    print("PASS\n")


if __name__ == "__main__":
    test_streaming_turn()
    test_steered_response()
    test_error_frame()
    test_failed_turn()
    test_non_streaming()
    print("All stream tests passed.")
