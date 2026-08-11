# Codex App Server

[English](README.md)

一个 Dify 工具插件，驱动
[codex-app-server](../README.md) HTTP 服务，把 codex 智能体的回答（含思考过程）
流式返回给用户。codex-app-server 封装了 codex `app-server` 的 JSON-RPC 协议，
一个常驻 `codex app-server` 进程即可服务所有对话，按 `app_id` + `user_id` 隔离。

## 工作原理

**Codex 对话** 工具向 `POST {server_url}/api/messages` 发送
`{query, conversation_id, app_id, user_id}`，并渲染 SSE 事件流：

- **流式输出开启（默认）** - 发送 `stream: true`。推理摘要、命令执行、文件变更
  与工具调用包裹在单个 `<think>…</think>` 块中，Dify 会渲染为可折叠的"思考"面板；
  智能体回答增量则作为普通正文流式输出。这与官方 OpenAI 插件
  （`models/llm/stream.py`）的做法一致：`<think>` 在第一段推理时惰性开启，在回答
  开始前关闭。
- **流式输出关闭** - 等待执行结束后一次性返回完整回答。

相同 `conversation_id` 的调用会续接同一个 codex 线程
（`thread/resume` + `turn/start`），智能体保持完整上下文。

### 结束标识与同步完成

codex-app-server 会转发 `turn/completed` 通知，随后追加一个合成的 `done` 汇总帧，
携带轮次 `status`（`completed` / `interrupted` / `failed`）。对话工具把 `done`
视为权威结束标识：在 codex 轮次真正结束之前流不会返回，因此当 Dify 工作流结束时，
codex 后端也已停止——终止是同步的。

### 下次继续

对话线程由 codex-app-server 持久化（SQLite 映射 + codex `CODEX_HOME` rollout）。
即使轮次被中断或失败，下次用相同 `conversation_id` 发消息仍会续接线程并开启新轮次。

### 同步终止

**Codex 终止对话** 工具发送空 `query` + `conversation_id`，触发 `turn/interrupt`
并*等待*运行中的轮次真正停止后才返回。当工作流需要保证 codex 轮次已停止时使用
（例如停止按钮或清理节点）。

## 配置

1. 运行 codex-app-server 服务（见 `../README.md`），默认监听
   `http://127.0.0.1:5040`。
2. 在 Dify 中添加本插件的供应商凭据：
   - **服务地址** - codex-app-server 基础地址，默认
     `http://host.docker.internal:5040`（插件运行在 Docker 中，访问宿主机服务用此地址）。
   - **API Key** - 仅当 codex-app-server 设置了 `CODEX_API_AUTH_TOKEN` 时需要。
3. 将 **Codex 对话** 工具加入工作流/智能体，传入 `query`、`conversation_id`、
   `app_id` 和 `user_id`。

四个输入均默认取对应的 `sys.*` 变量，在 chatflow 中可自动接入当前对话。

## 工具

| 工具 | 说明 |
| --- | --- |
| `codex_chat` | 发送消息并流式返回智能体回答与思考 |
| `codex_terminate` | 同步停止某个对话中正在运行的轮次 |

## 输出

| 名称 | 说明 |
| --- | --- |
| `text` | 智能体回答，流式输出开启时边产生边输出 |
| `json` | （仅终止工具）codex-app-server 返回的原始终止响应 |
