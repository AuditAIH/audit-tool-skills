# codex-app-server

把 Codex 的 `app-server` JSON-RPC 协议封装成一个轻量 HTTP API，支持创建/继续对话、流式输出、插入消息（steer）、终止、删除对话和文件上传。

底层维护一个常驻 `codex app-server` 进程（stdio JSON-RPC），通过 `thread/start`、`thread/resume`、`turn/start`、`turn/steer`、`turn/interrupt`、`thread/delete` 驱动对话。

## 架构与并发

- **一个端口服务所有用户**：一个 HTTP server + 一个常驻 `codex app-server` 进程，所有用户/项目并发共用。
- **多用户同时问答**：已支持。每个对话 = 一个独立 thread，不同对话并发处理，互不阻塞。
- **隔离方式**：靠 `app_id`（项目）+ `user_id`（用户）划分工作目录和对话归属。
  - 工作目录：`<workspace_base>/<app_id>/workspace/<user_id>/`
  - 对话归属：`user_id` 校验，不同用户互不可见
- ⚠️ **暂未做进程级隔离**：所有用户共用同一个 `codex app-server` 进程和同一套 `CODEX_HOME`（即同一个模型 API key / 额度）。如需每个项目独立 key/认证/进程，需另做进程管理器（未实现）。

## 编译

```bash
go build -o codex-app-server .
# 静态二进制（便于容器）：
CGO_ENABLED=0 go build -o codex-app-server .
```

## 运行

```bash
./codex-app-server              # 默认读当前目录 .env
./codex-app-server -config /path/to/.env
```

配置项见 `.env.example`。

## 接口列表

基址 `http://<host>:5040`，前缀默认 `/api`（`CODEX_API_PREFIX` 可改）。所有响应为英文。若设置了 `CODEX_API_AUTH_TOKEN`，请求需带 `Authorization: Bearer <token>`。

---

### 1. 发送消息 / 创建 / 继续 / 插入 / 终止

`POST /api/messages`

请求体：

| 字段 | 类型 | 说明 |
|------|------|------|
| `query` | string | 用户消息。**空 + 有 conversation_id = 终止对话** |
| `conversation_id` | string | 留空=自动生成新对话；传值=续接/插入/终止该对话 |
| `app_id` | string | 项目标识，用于派生工作目录 |
| `user_id` | string | 用户标识，用于工作目录和归属校验 |
| `cwd` | string | 直接指定工作目录（优先级最高） |
| `stream` | bool | true=SSE 流式输出 |

行为：
- **新对话**：`conversation_id` 为空或不存在的 store 记录 -> `thread/start` + `turn/start`
- **继续对话**：`conversation_id` 已有 thread，且当前无活跃 turn -> `thread/resume` + `turn/start`（新轮次）
- **插入消息（steer）**：`conversation_id` 有活跃 turn -> `turn/steer`，即时返回 `status:"steered"`，消息插进正在跑的 turn（不开新轮次）
- **终止对话**：`query` 为空 + `conversation_id` -> `turn/interrupt`，停止活跃 turn

工作目录解析优先级：`cwd` > `app_id`/`user_id` 派生 > `CODEX_API_WORK_DIR` > 进程目录。

**创建对话**
```bash
curl -X POST http://127.0.0.1:5040/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"query":"你好","conversation_id":"","app_id":"myapp","user_id":"u001"}'
```
响应：
```json
{"conversation_id":"...","thread_id":"...","turn_id":"...","message":"...","status":"completed"}
```

**继续对话**（带上一次的 conversation_id）
```bash
curl -X POST http://127.0.0.1:5040/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"query":"接着说","conversation_id":"<id>","app_id":"myapp","user_id":"u001"}'
```

**流式输出**
```bash
curl -N -X POST http://127.0.0.1:5040/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"query":"写首诗","conversation_id":"","app_id":"myapp","user_id":"u001","stream":true}'
```
每条 app-server 通知（`turn/*`、`item/*`）作为一个 SSE `data:` 帧，最后追加一个 `done` 汇总帧。

**插入消息**（长任务跑着时，同一 conversation_id）
```bash
curl -X POST http://127.0.0.1:5040/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"query":"顺便提一下大海","conversation_id":"<id>","app_id":"myapp","user_id":"u001"}'
```
响应：`{"status":"steered","message":"","turn_id":"..."}`
> steer 是即时确认，插入内容的实际输出在那个 turn 的流式结果里。

**终止对话**（空 query + conversation_id + user_id）
```bash
curl -X POST http://127.0.0.1:5040/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"query":"","conversation_id":"<id>","app_id":"myapp","user_id":"u001"}'
```
响应：
- `{"status":"terminated","message":"conversation manually terminated"}`
- 无活跃 turn：`{"status":"no_active_turn","message":"no active turn to terminate"}`
- 对话不存在：`{"status":"no_conversation","message":"conversation not found"}`

---

### 2. 删除对话

`DELETE /api/conversations`

`conversation_id` 或 `thread_id` 任传一个即可删除（永久删除线程及历史）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | string | 二选一 |
| `thread_id` | string | 二选一 |
| `user_id` | string | 归属校验（有记录时） |

```bash
curl -X DELETE http://127.0.0.1:5040/api/conversations \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"<id>","user_id":"u001"}'
# 或按 thread_id
curl -X DELETE http://127.0.0.1:5040/api/conversations \
  -H 'Content-Type: application/json' \
  -d '{"thread_id":"<tid>","user_id":"u001"}'
```
响应：
- `{"status":"deleted","message":"conversation deleted"}`
- 不存在：`{"status":"no_conversation","message":"conversation not found"}`
- user 不匹配：403 `{"error":"you are not allowed to access this conversation, please start a new one"}`

流程：先 `turn/interrupt` 停活跃 turn（如有）-> `thread/delete` 删线程 -> 删 SQLite 记录。

---

### 3. 上传文件

`POST /api/upload`（multipart，字段名 `file`）

单文件上传，按内容 MD5 + 原后缀重命名，同名覆盖，存到工作目录下 `uploads/`，返回绝对路径。

| 表单字段 | 说明 |
|----------|------|
| `file` | 文件（必填） |
| `app_id` / `user_id` / `cwd` | 决定存到哪个工作目录（同消息接口的解析规则） |

```bash
curl -X POST http://127.0.0.1:5040/api/upload \
  -F "file=@/path/to/report.pdf" \
  -F "app_id=myapp" -F "user_id=u001"
```
响应：
```json
{"path":"/abs/.../uploads/<md5>.pdf","filename":"<md5>.pdf","md5":"...","size":12345,"original":"report.pdf"}
```
> 协议不支持直接传文件进对话。图片可用返回的 path 作为 `localImage`，其他文件在 `query` 里引用路径让 agent 读取（agent 在工作目录有文件系统访问权）。

---

### 4. 健康检查

`GET /healthz` -> `{"status":"ok"}`

## 配置项

见 `.env.example`。关键项：

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEX_API_PORT` | 5040 | 监听端口 |
| `CODEX_API_PREFIX` | api | 路由前缀 |
| `CODEX_API_WORKSPACE_BASE` | ./home | 工作目录基底 |
| `CODEX_API_DB` | ./codex-app-server.db | SQLite 路径 |
| `CODEX_API_BIN` | codex | codex 二进制 |
| `CODEX_API_CODEX_HOME` | ~/.codex | 认证/会话数据 |
| `CODEX_API_APPROVAL_POLICY` | never | 审批策略 |
| `CODEX_API_SANDBOX` | dangerFullAccess | 沙箱模式 |
| `CODEX_API_MODEL` | (空) | 模型覆盖 |
| `CODEX_API_AUTH_TOKEN` | (空) | Bearer 鉴权 |
| `CODEX_API_LOG_LEVEL` | request | error/request/output |

`CODEX_API_ENV_FOO=bar` 会把 `FOO=bar` 注入给 codex 子进程。

## Docker 部署

`docker/docker-compose.agent.yml` 的 `local_sandbox` 服务挂载本二进制并在 5040 端口运行，与 shellctl（5004）同容器。codex CLI 二进制通过只读挂载提供。环境变量在 compose 里按 `.env.example` 设置。
