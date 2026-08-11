"""Unit test for ThinkStreamFormatter event rendering (no network needed).

Usage: .venv/bin/python working/test_formatter.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.codex_chat import ThinkStreamFormatter  # noqa: E402


def render(events):
    fmt = ThinkStreamFormatter()
    out = []
    for ev in events:
        chunk = fmt.format_event(ev)
        if chunk:
            out.append(chunk)
    tail = fmt.finalize()
    if tail:
        out.append(tail)
    return "".join(out)


def test_basic_flow():
    events = [
        {"method": "turn/started", "turn": {"id": "t1", "status": "inProgress"}},
        {"method": "item/started", "item": {"type": "reasoning", "id": "r1"}},
        {"method": "item/reasoning/summaryTextDelta", "delta": "Let me think "},
        {"method": "item/reasoning/summaryTextDelta", "delta": "about this."},
        {"method": "item/completed", "item": {"type": "reasoning", "id": "r1"}},
        {"method": "item/started", "item": {"type": "commandExecution", "id": "c1"}},
        {"method": "item/completed", "item": {
            "type": "commandExecution", "id": "c1",
            "command": "ls -la", "status": "completed",
            "aggregatedOutput": "total 0\ndrwxr-xr-x 2 root root 40 Aug 11 10:00 .",
        }},
        {"method": "item/started", "item": {"type": "agentMessage", "id": "a1"}},
        {"method": "item/agentMessage/delta", "delta": "I created "},
        {"method": "item/agentMessage/delta", "delta": "the files."},
        {"method": "item/completed", "item": {"type": "agentMessage", "id": "a1", "text": "I created the files."}},
        {"method": "turn/completed", "turn": {"id": "t1", "status": "completed"}},
    ]
    out = render(events)
    print("=== test_basic_flow output ===")
    print(repr(out))
    print(out)
    assert "<think>" in out, "missing <think> open"
    assert "</think>" in out, "missing </think> close"
    assert "Let me think about this." in out, "reasoning not streamed"
    assert "$ ls -la" in out, "command not rendered"
    assert "total 0" in out, "command output not rendered"
    assert "I created the files." in out, "agent message not streamed"
    # think must close before the answer
    assert out.index("</think>") < out.index("I created"), "think not closed before answer"
    print("PASS: test_basic_flow\n")


def test_multiple_agent_messages():
    events = [
        {"method": "item/agentMessage/delta", "delta": "First answer."},
        {"method": "item/completed", "item": {"type": "agentMessage", "id": "a1", "text": "First answer."}},
        {"method": "item/started", "item": {"type": "agentMessage", "id": "a2"}},
        {"method": "item/agentMessage/delta", "delta": "Second answer."},
        {"method": "item/completed", "item": {"type": "agentMessage", "id": "a2", "text": "Second answer."}},
    ]
    out = render(events)
    print("=== test_multiple_agent_messages output ===")
    print(repr(out))
    assert "First answer." in out
    assert "Second answer." in out
    # messages separated by blank line
    assert "First answer.\n\nSecond answer." in out or "First answer." in out
    print("PASS: test_multiple_agent_messages\n")


def test_reasoning_only_then_finalize():
    events = [
        {"method": "item/reasoning/summaryTextDelta", "delta": "Just thinking, no answer yet."},
    ]
    out = render(events)
    print("=== test_reasoning_only_then_finalize output ===")
    print(repr(out))
    assert "<think>" in out
    assert "</think>" in out, "finalize must close unclosed think"
    assert "Just thinking, no answer yet." in out
    print("PASS: test_reasoning_only_then_finalize\n")


def test_plan_rendering():
    events = [
        {"method": "turn/plan/updated", "explanation": "My plan", "plan": [
            {"step": "Read files", "status": "completed"},
            {"step": "Write code", "status": "inProgress"},
            {"step": "Run tests", "status": "pending"},
        ]},
    ]
    out = render(events)
    print("=== test_plan_rendering output ===")
    print(repr(out))
    assert "<think>" in out
    assert "My plan" in out
    assert "[x] Read files" in out
    assert "[>] Write code" in out
    assert "[ ] Run tests" in out
    print("PASS: test_plan_rendering\n")


def test_file_change():
    events = [
        {"method": "item/completed", "item": {
            "type": "fileChange", "id": "f1", "status": "completed",
            "changes": [
                {"path": "src/a.py", "kind": {"type": "create"}},
                {"path": "src/b.py", "kind": "modify"},
            ],
        }},
    ]
    out = render(events)
    print("=== test_file_change output ===")
    print(repr(out))
    assert "create src/a.py" in out
    assert "modify src/b.py" in out
    print("PASS: test_file_change\n")


def test_interrupted_no_error():
    """An interrupted turn should not raise; output still finalized."""
    events = [
        {"method": "item/agentMessage/delta", "delta": "partial..."},
        {"method": "turn/completed", "turn": {"id": "t1", "status": "interrupted"}},
        {"method": "done", "status": "interrupted", "conversation_id": "c1"},
    ]
    out = render(events)
    print("=== test_interrupted_no_error output ===")
    print(repr(out))
    assert "partial..." in out
    print("PASS: test_interrupted_no_error\n")


if __name__ == "__main__":
    test_basic_flow()
    test_multiple_agent_messages()
    test_reasoning_only_then_finalize()
    test_plan_rendering()
    test_file_change()
    test_interrupted_no_error()
    print("All formatter tests passed.")
