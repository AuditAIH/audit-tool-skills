# Codex App Server

[中文](README.zh-Hans.md)

A Dify tool plugin that drives a
[codex-app-server](../README.md) HTTP service and streams the codex agent's
reply (with reasoning) back to the user. The codex-app-server wraps the codex
`app-server` JSON-RPC protocol, so a single long-lived `codex app-server`
process serves all conversations, each isolated by `app_id` + `user_id`.

## How it works

The **Codex Chat** tool sends `POST {server_url}/api/messages` with
`{query, conversation_id, app_id, user_id}` and renders the SSE event stream:

- **Stream Output enabled (default)** — `stream: true` is sent. Reasoning
  summaries, command executions, file changes and tool calls are wrapped in a
  single `<think>…</think>` block that Dify renders as a collapsible
  "thinking" panel; agent message deltas stream as normal answer text. This
  mirrors the official OpenAI plugin's convention (`models/llm/stream.py`):
  `<think>` opens lazily on the first reasoning piece and closes right before
  the answer.
- **Stream Output disabled** — waits for the run to finish and returns the
  full reply at once.

Calls sharing the same `conversation_id` resume the same codex thread
(`thread/resume` + `turn/start`), so the agent keeps full context across
turns.

### End markers & synchronous completion

The codex-app-server forwards every `turn/completed` notification and then
appends a synthetic `done` summary frame carrying the turn `status`
(`completed` / `interrupted` / `failed`). The chat tool treats `done` as the
authoritative end marker: the stream does not return until the codex turn has
actually finished, so when the Dify workflow ends the codex backend is no
longer running — termination is synchronous.

### Continue next time

The conversation thread is persisted by codex-app-server (SQLite mapping +
codex `CODEX_HOME` rollout). Even after a turn is interrupted or fails, the
next message with the same `conversation_id` resumes the thread and starts a
fresh turn.

### Synchronous termination

The **Codex Terminate** tool sends an empty `query` with a
`conversation_id`, which triggers `turn/interrupt` and *waits* for the
running turn to actually stop before returning. Use it when a workflow must
guarantee the codex turn is stopped (e.g. a stop button or a cleanup node).

## Setup

1. Run the codex-app-server service (see `../README.md`), by default it
   listens on `http://127.0.0.1:5040`.
2. In Dify, add this plugin's provider credentials:
   - **Server URL** — base URL of codex-app-server, defaults to
     `http://host.docker.internal:5040` (the plugin daemon runs in Docker;
     this reaches a service running on the host).
   - **API Key** — only when codex-app-server sets `CODEX_API_AUTH_TOKEN`.
3. Add the **Codex Chat** tool to a workflow/agent and pass `query`,
   `conversation_id`, `app_id` and `user_id`.

All four inputs default to the matching `sys.*` variables, so in a chatflow
the tool wires itself to the current conversation out of the box.

## Tools

| tool | description |
| --- | --- |
| `codex_chat` | send a message and stream the agent reply + reasoning |
| `codex_terminate` | synchronously stop the active turn for a conversation |

## Outputs

| name | description |
| --- | --- |
| `text` | the agent reply, streamed while produced when Stream Output is on |
| `json` | (terminate only) the raw termination response from codex-app-server |
