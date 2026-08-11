"""Local smoke test: invoke the tools against a live codex-app-server service.

Usage: .venv/bin/python working/test_local.py
Not packaged (.difyignore excludes working/).
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.codex_chat import CodexChatTool  # noqa: E402
from tools.codex_terminate import CodexTerminateTool  # noqa: E402

from dify_plugin.entities.tool import ToolInvokeMessage  # noqa: E402

SERVER = "http://127.0.0.1:5040"
CREDS = {"server_url": SERVER, "api_key": ""}
CONV = "dify-plugin-test-1"


def make_tool(cls):
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=CREDS)
    tool.response_type = ToolInvokeMessage
    return tool


def test_chat():
    tool = make_tool(CodexChatTool)
    params = {
        "query": "创建两个文件 a.txt 和 b.txt，各写一行 hello，然后告诉我你做了什么",
        "conversation_id": CONV,
        "user_id": "plugin-test",
        "app_id": "dify-plugin-test",
        "stream": True,
    }
    start = time.time()
    for msg in tool._invoke(params):
        if msg.type.value == "text":
            print(f"[text +{time.time() - start:5.1f}s] {msg.message.text!r}")
        else:
            print(f"[{msg.type}] {msg}")
    print(f"chat elapsed: {time.time() - start:.1f}s")


def test_terminate():
    tool = make_tool(CodexTerminateTool)
    params = {
        "conversation_id": CONV,
        "user_id": "plugin-test",
        "app_id": "dify-plugin-test",
    }
    for msg in tool._invoke(params):
        if msg.type.value == "text":
            print(f"[text] {msg.message.text!r}")
        elif msg.type.value == "json":
            print(f"[json] {msg.message.json_object}")
        else:
            print(f"[{msg.type}] {msg}")


if __name__ == "__main__":
    test_chat()
    # Uncomment to test synchronous termination of the conversation above:
    # test_terminate()
