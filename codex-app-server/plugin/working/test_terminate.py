"""Unit test for the CodexTerminateTool (mocked HTTP).

Usage: .venv/bin/python working/test_terminate.py
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from dify_plugin.entities.tool import ToolInvokeMessage  # noqa: E402
from tools.codex_terminate import CodexTerminateTool  # noqa: E402


def make_tool():
    tool = CodexTerminateTool.__new__(CodexTerminateTool)
    tool.runtime = SimpleNamespace(credentials={"server_url": "http://test:5040", "api_key": "secret"})
    tool.response_type = ToolInvokeMessage
    return tool


def test_terminate_sends_empty_query():
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "conversation_id": "c1", "thread_id": "th1", "turn_id": "t1",
            "status": "terminated", "message": "conversation manually terminated",
        }
        return resp

    with patch.object(httpx, "post", side_effect=fake_post):
        tool = make_tool()
        msgs = list(tool._invoke({
            "conversation_id": "c1", "user_id": "u1", "app_id": "a1",
        }))

    print("=== test_terminate_sends_empty_query ===")
    print("captured url:", captured["url"])
    print("captured json:", captured["json"])
    print("auth header:", captured["headers"].get("Authorization"))

    # The key requirement: empty query triggers turn/interrupt (sync terminate).
    assert captured["json"]["query"] == "", "query must be empty for termination"
    assert captured["json"]["conversation_id"] == "c1"
    assert captured["json"]["user_id"] == "u1"
    assert captured["json"]["app_id"] == "a1"
    assert captured["url"].endswith("/api/messages")
    assert captured["headers"]["Authorization"] == "Bearer secret"

    text_msg = [m for m in msgs if m.type.value == "text"]
    json_msg = [m for m in msgs if m.type.value == "json"]
    assert text_msg, "should emit a text message"
    assert "terminated" in text_msg[0].message.text
    assert json_msg, "should emit a json message"
    assert json_msg[0].message.json_object["status"] == "terminated"
    print("text:", text_msg[0].message.text)
    print("json:", json_msg[0].message.json_object)
    print("PASS\n")


def test_terminate_no_active_turn():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "no_active_turn", "message": "no active turn to terminate"}
    with patch.object(httpx, "post", return_value=resp):
        tool = make_tool()
        msgs = list(tool._invoke({
            "conversation_id": "c1", "user_id": "u1",
        }))
    text = "".join(m.message.text for m in msgs if m.type.value == "text")
    print("=== test_terminate_no_active_turn ===")
    print("text:", text)
    assert "no_active_turn" in text
    print("PASS\n")


if __name__ == "__main__":
    test_terminate_sends_empty_query()
    test_terminate_no_active_turn()
    print("All terminate tests passed.")
