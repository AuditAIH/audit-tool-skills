package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// rpcError is the JSON-RPC error object.
type rpcError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

// rpcFrame is a generic on-wire message. The app-server protocol omits the
// "jsonrpc":"2.0" header, so we omit it here too.
type rpcFrame struct {
	Method string          `json:"method,omitempty"`
	ID     json.RawMessage `json:"id,omitempty"`
	Params json.RawMessage `json:"params,omitempty"`
	Result json.RawMessage `json:"result,omitempty"`
	Error  *rpcError       `json:"error,omitempty"`
}

// eventQueue is an unbounded, context-aware FIFO of notification events.
// It never blocks the producer (the single read loop), so a slow consumer
// on one thread cannot stall dispatch for other threads.
type eventQueue struct {
	notify chan struct{}
	mu     sync.Mutex
	buf    []map[string]any
	closed bool
}

func newEventQueue() *eventQueue {
	return &eventQueue{notify: make(chan struct{}, 1)}
}

func (q *eventQueue) push(e map[string]any) {
	q.mu.Lock()
	q.buf = append(q.buf, e)
	q.mu.Unlock()
	select {
	case q.notify <- struct{}{}:
	default:
	}
}

func (q *eventQueue) recv(ctx context.Context) (map[string]any, bool) {
	for {
		q.mu.Lock()
		if len(q.buf) > 0 {
			e := q.buf[0]
			q.buf = q.buf[1:]
			q.mu.Unlock()
			return e, true
		}
		if q.closed {
			q.mu.Unlock()
			return nil, false
		}
		q.mu.Unlock()
		select {
		case <-q.notify:
		case <-ctx.Done():
			return nil, false
		}
	}
}

func (q *eventQueue) close() {
	q.mu.Lock()
	q.closed = true
	q.mu.Unlock()
	select {
	case q.notify <- struct{}{}:
	default:
	}
}

// TurnResult summarizes one turn/start ... turn/completed cycle.
type TurnResult struct {
	TurnID  string
	Status  string // completed | interrupted | failed
	Message string // last agent message text
	Error   string // turn error message, if any
}

// Client wraps a long-lived `codex app-server` stdio process and exposes the
// small subset of the JSON-RPC protocol we need: initialize, thread/start,
// thread/resume and turn/start, with notification routing keyed by threadId.
type Client struct {
	cfg   Config
	ctx   context.Context
	cncl  context.CancelFunc
	cmd   *exec.Cmd
	stdin io.WriteCloser

	wmu    sync.Mutex // guards stdin writes
	nextID atomic.Int64

	mu      sync.Mutex // guards pending, subs and run state
	pending map[int64]chan *rpcFrame
	subs    map[string]*eventQueue
	activeTurns sync.Map // threadID -> active turnID (set while a turn runs)
	ready   bool
	dead    bool

	startMu sync.Mutex // serializes (re)start attempts
}

func NewClient(cfg Config) *Client {
	ctx, cancel := context.WithCancel(context.Background())
	return &Client{
		cfg:     cfg,
		ctx:     ctx,
		cncl:    cancel,
		pending: make(map[int64]chan *rpcFrame),
		subs:    make(map[string]*eventQueue),
	}
}

// Start spawns the app-server process and performs the initialize handshake.
// It is safe to call again after the process has died (reconnect).
func (c *Client) Start(ctx context.Context) error {
	return c.ensureRunning(ctx)
}

func (c *Client) Stop() {
	if c.cncl != nil {
		c.cncl()
	}
	c.wmu.Lock()
	if c.stdin != nil {
		_ = c.stdin.Close()
	}
	c.wmu.Unlock()
	if c.cmd != nil && c.cmd.Process != nil {
		_ = c.cmd.Process.Kill()
	}
}

func (c *Client) ensureRunning(ctx context.Context) error {
	c.mu.Lock()
	if c.ready && !c.dead {
		c.mu.Unlock()
		return nil
	}
	c.mu.Unlock()

	c.startMu.Lock()
	defer c.startMu.Unlock()
	c.mu.Lock()
	if c.ready && !c.dead {
		c.mu.Unlock()
		return nil
	}
	c.mu.Unlock()
	return c.start(ctx)
}

func (c *Client) start(ctx context.Context) error {
	args := []string{"app-server", "--listen", "stdio://"}
	if c.cfg.Yolo {
		// --yolo is a global flag (must precede the subcommand). It is
		// equivalent to --dangerously-bypass-approvals-and-sandbox:
		// skips all approvals and bypasses the sandbox. --disable
		// unified_exec is also needed in Docker: the unified-exec
		// process uses bwrap (can't create user namespaces) + bundled
		// zsh (needs GLIBC_2.38). Without it, app-server falls back to
		// direct exec — same code path as codex exec --yolo.
		args = []string{"--yolo", "app-server", "--disable", "unified_exec", "--listen", "stdio://"}
	}
	cmd := exec.CommandContext(c.ctx, c.cfg.Bin, args...)
	cmd.Env = childEnv(c.cfg)

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("stdin pipe: %w", err)
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("stdout pipe: %w", err)
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start app-server: %w", err)
	}

	c.cmd = cmd
	c.stdin = stdin
	c.dead = false

	go c.readLoop(stdout, &stderr)
	go c.reaper(&stderr)

	if err := c.initialize(ctx); err != nil {
		// kill the half-started process so a retry is clean
		_ = cmd.Process.Kill()
		return err
	}
	c.mu.Lock()
	c.ready = true
	c.mu.Unlock()
	logRequestf("app-server connected (pid %d)", cmd.Process.Pid)
	return nil
}

// reaper waits for the process to exit and tears down client state so the
// next request triggers a reconnect.
func (c *Client) reaper(stderr *bytes.Buffer) {
	_ = c.cmd.Wait()
	c.mu.Lock()
	c.dead = true
	c.ready = false
	for id, ch := range c.pending {
		select {
		case ch <- &rpcFrame{Error: &rpcError{Code: -1, Message: "app-server process exited"}}:
		default:
		}
		delete(c.pending, id)
	}
	for _, q := range c.subs {
		q.close()
	}
	c.subs = make(map[string]*eventQueue)
	c.activeTurns.Range(func(k, _ any) bool {
		c.activeTurns.Delete(k)
		return true
	})
	c.mu.Unlock()
	if s := strings.TrimSpace(stderr.String()); s != "" {
		logErrorf("app-server stderr: %s", s)
	}
	logErrorf("app-server process exited")
}

func (c *Client) initialize(ctx context.Context) error {
	ictx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	result, err := c.call(ictx, "initialize", map[string]any{
		"clientInfo": map[string]any{
			"name":    "codex_app_server_api",
			"title":   "Codex App Server API",
			"version": "0.1.0",
		},
	})
	if err != nil {
		return fmt.Errorf("initialize: %w", err)
	}
	var res struct {
		UserAgent      string `json:"userAgent"`
		PlatformFamily string `json:"platformFamily"`
		PlatformOS     string `json:"platformOs"`
	}
	_ = json.Unmarshal(result, &res)
	logRequestf("app-server initialized: %s (%s/%s)", res.UserAgent, res.PlatformFamily, res.PlatformOS)
	if err := c.notify("initialized", map[string]any{}); err != nil {
		return fmt.Errorf("send initialized: %w", err)
	}
	return nil
}

// readLoop decodes newline-delimited JSON from the app-server stdout and
// dispatches each frame to its handler.
func (c *Client) readLoop(stdout io.Reader, stderr *bytes.Buffer) {
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 0, 64*1024), 32*1024*1024)
	for scanner.Scan() {
		line := bytes.TrimSpace(scanner.Bytes())
		if len(line) == 0 {
			continue
		}
		var f rpcFrame
		if json.Unmarshal(line, &f) != nil {
			logOutputf("unparseable: %s", truncate(string(line), 300))
			continue
		}
		c.dispatch(line, &f)
	}
}

func (c *Client) dispatch(raw []byte, f *rpcFrame) {
	hasMethod := f.Method != ""
	hasID := len(f.ID) > 0

	// Server-initiated request (e.g. an approval) -> auto-respond.
	if hasMethod && hasID {
		c.handleServerRequest(f)
		return
	}
	// Response to one of our requests.
	if hasID && !hasMethod {
		id, _ := parseID(f.ID)
		c.mu.Lock()
		ch, ok := c.pending[id]
		if ok {
			delete(c.pending, id)
		}
		c.mu.Unlock()
		if ok {
			select {
			case ch <- f:
			default:
			}
		}
		return
	}
	// Notification -> route to the active turn's event queue by threadId.
	if hasMethod && !hasID {
		var params map[string]any
		if len(f.Params) > 0 {
			_ = json.Unmarshal(f.Params, &params)
		}
		if params == nil {
			params = map[string]any{}
		}
		params["method"] = f.Method
		logOutputf("notify %s %s", f.Method, truncate(string(raw), 300))
		if tid, _ := params["threadId"].(string); tid != "" {
			c.mu.Lock()
			q, ok := c.subs[tid]
			c.mu.Unlock()
			if ok {
				q.push(params)
			}
		}
		return
	}
}

// handleServerRequest auto-approves command/file/permission requests and
// declines interactive prompts we can't satisfy. With approvalPolicy "never"
// + dangerFullAccess these are not normally sent, but we handle them so a
// turn never deadlocks waiting on the client.
func (c *Client) handleServerRequest(f *rpcFrame) {
	var params map[string]any
	if len(f.Params) > 0 {
		_ = json.Unmarshal(f.Params, &params)
	}
	logOutputf("server-request %s", f.Method)
	result := autoRespond(f.Method, params)
	_ = c.send(map[string]any{"id": json.RawMessage(f.ID), "result": result})
}

func autoRespond(method string, params map[string]any) any {
	switch {
	case strings.Contains(method, "permissions/requestApproval"):
		granted := map[string]any{}
		if r, ok := params["requested"].(map[string]any); ok {
			granted = r
		}
		return map[string]any{"permissions": granted, "scope": "session"}
	case strings.Contains(method, "requestApproval"):
		return map[string]any{"decision": "accept"}
	case strings.Contains(method, "elicitation"):
		return map[string]any{"action": "decline"}
	case strings.Contains(method, "requestUserInput"):
		return map[string]any{"answers": []any{}}
	default:
		return map[string]any{}
	}
}

// call sends a JSON-RPC request and waits for the matching response. It must
// only be called when the process is known to be running (callers ensure this
// via ensureRunning); calling ensureRunning here would re-enter startMu while
// initialize is in flight and deadlock.
func (c *Client) call(ctx context.Context, method string, params any) (json.RawMessage, error) {
	id := c.nextID.Add(1)
	ch := make(chan *rpcFrame, 1)
	c.mu.Lock()
	c.pending[id] = ch
	c.mu.Unlock()

	if err := c.send(map[string]any{"method": method, "id": id, "params": params}); err != nil {
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return nil, err
	}

	select {
	case resp := <-ch:
		if resp.Error != nil {
			return resp.Result, fmt.Errorf("rpc %s: [%d] %s", method, resp.Error.Code, resp.Error.Message)
		}
		return resp.Result, nil
	case <-ctx.Done():
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return nil, ctx.Err()
	}
}

func (c *Client) notify(method string, params any) error {
	return c.send(map[string]any{"method": method, "params": params})
}

func (c *Client) send(msg any) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	c.wmu.Lock()
	defer c.wmu.Unlock()
	if c.stdin == nil {
		return fmt.Errorf("app-server stdin closed")
	}
	_, err = c.stdin.Write(data)
	return err
}

// StartThread creates a new conversation thread rooted at cwd.
func (c *Client) StartThread(ctx context.Context, cwd string) (string, error) {
	if err := c.ensureRunning(ctx); err != nil {
		return "", err
	}
	params := map[string]any{}
	if cwd != "" {
		params["cwd"] = cwd
	}
	if c.cfg.Model != "" {
		params["model"] = c.cfg.Model
	}
	// When not using --yolo, pass sandbox/approval via the protocol.
	// thread/start uses the legacy "sandbox" string field (kebab-case).
	if !c.cfg.Yolo {
		params["approvalPolicy"] = c.cfg.ApprovalPolicy
		if sb := sandboxToConfig(c.cfg.Sandbox); sb != "" {
			params["sandbox"] = sb
		}
	}
	result, err := c.call(ctx, "thread/start", params)
	if err != nil {
		return "", err
	}
	var res struct {
		Thread struct {
			ID string `json:"id"`
		} `json:"thread"`
	}
	if err := json.Unmarshal(result, &res); err != nil {
		return "", fmt.Errorf("parse thread/start: %w", err)
	}
	if res.Thread.ID == "" {
		return "", fmt.Errorf("thread/start returned empty thread id")
	}
	return res.Thread.ID, nil
}

// sandboxToConfig maps protocol sandbox names (camelCase) to config.toml
// values (kebab-case). Returns "" for modes with no config equivalent.
func sandboxToConfig(s string) string {
	switch s {
	case "dangerFullAccess":
		return "danger-full-access"
	case "workspaceWrite":
		return "workspace-write"
	case "readOnly":
		return "read-only"
	default:
		return ""
	}
}

// ResumeThread reopens an existing thread so the next turn appends to it.
func (c *Client) ResumeThread(ctx context.Context, threadID string) error {
	if err := c.ensureRunning(ctx); err != nil {
		return err
	}
	_, err := c.call(ctx, "thread/resume", map[string]any{"threadId": threadID})
	return err
}

// Steer appends user input to the active in-flight turn on threadID without
// starting a new turn (natural Codex "type while it works"). It returns the
// active turn id and steered=true on success; steered=false when there is no
// active turn to steer (caller should start a new turn instead).
func (c *Client) Steer(ctx context.Context, threadID, query string) (turnID string, steered bool, err error) {
	if err := c.ensureRunning(ctx); err != nil {
		return "", false, err
	}
	v, ok := c.activeTurns.Load(threadID)
	if !ok {
		return "", false, nil
	}
	turnID, _ = v.(string)
	if turnID == "" {
		return "", false, nil
	}
	_, err = c.call(ctx, "turn/steer", map[string]any{
		"threadId":       threadID,
		"input":          []map[string]any{{"type": "text", "text": query}},
		"expectedTurnId": turnID,
	})
	if err != nil {
		// turn likely just finished; drop the stale entry and let caller
		// fall back to a fresh turn.
		c.activeTurns.Delete(threadID)
		return turnID, false, err
	}
	return turnID, true, nil
}



// Interrupt cancels the active in-flight turn on threadID (if any). It
// returns the interrupted turn id and interrupted=true when an active turn
// was cancelled; interrupted=false when there is no active turn. After the
// interrupt is accepted it waits briefly for the running turn to finish so a
// follow-up request does not race with it.
func (c *Client) Interrupt(ctx context.Context, threadID string) (turnID string, interrupted bool, err error) {
	if err := c.ensureRunning(ctx); err != nil {
		return "", false, err
	}
	v, ok := c.activeTurns.Load(threadID)
	if !ok {
		return "", false, nil
	}
	turnID, _ = v.(string)
	if turnID == "" {
		return "", false, nil
	}
	if _, err = c.call(ctx, "turn/interrupt", map[string]any{
		"threadId": threadID,
		"turnId":   turnID,
	}); err != nil {
		c.activeTurns.Delete(threadID)
		return turnID, false, err
	}
	// Wait for the running turn to observe turn/completed (status
	// "interrupted") and clear the active-turn marker.
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if _, ok := c.activeTurns.Load(threadID); !ok {
			break
		}
		select {
		case <-ctx.Done():
			return turnID, true, nil
		default:
		}
		time.Sleep(50 * time.Millisecond)
	}
	return turnID, true, nil
}

// DeleteThread permanently deletes a thread and its spawned descendant
// threads from the app-server store. Missing rollout files are treated as
// already deleted, so this is safe to call for unknown ids.
func (c *Client) DeleteThread(ctx context.Context, threadID string) error {
	if err := c.ensureRunning(ctx); err != nil {
		return err
	}
	_, err := c.call(ctx, "thread/delete", map[string]any{"threadId": threadID})
	return err
}
// RunTurn starts a turn on threadID with the given user query and streams
// notifications until turn/completed. onEvent (if non-nil) receives every
// notification for this thread, merged with its method name.
func (c *Client) RunTurn(ctx context.Context, threadID, query string, onEvent func(map[string]any)) (*TurnResult, error) {
	if err := c.ensureRunning(ctx); err != nil {
		return nil, err
	}

	q := newEventQueue()
	c.mu.Lock()
	c.subs[threadID] = q
	c.mu.Unlock()
	defer func() {
		c.mu.Lock()
		delete(c.subs, threadID)
		c.mu.Unlock()
		q.close()
	}()

	turnParams := map[string]any{
		"threadId": threadID,
		"input":    []map[string]any{{"type": "text", "text": query}},
	}
	// Yolo: externalSandbox tells codex to skip its own sandbox (bwrap/
	// landlock) entirely — correct for Docker where bwrap can't create
	// user namespaces. Combined with the --yolo global flag + --disable
	// unified_exec, every command runs via direct exec (codex exec --yolo
	// equivalent). Non-yolo: pass configured sandbox/approval per turn.
	if c.cfg.Yolo {
		turnParams["sandboxPolicy"] = map[string]any{"type": "externalSandbox", "networkAccess": "enabled"}
	} else {
		turnParams["approvalPolicy"] = c.cfg.ApprovalPolicy
		turnParams["sandboxPolicy"] = map[string]any{"type": c.cfg.Sandbox}
	}
	result, err := c.call(ctx, "turn/start", turnParams)
	if err != nil {
		return nil, err
	}
	var tr struct {
		Turn struct {
			ID     string `json:"id"`
			Status string `json:"status"`
		} `json:"turn"`
	}
	_ = json.Unmarshal(result, &tr)

	res := &TurnResult{TurnID: tr.Turn.ID, Status: tr.Turn.Status}
	if res.TurnID != "" {
		c.activeTurns.Store(threadID, res.TurnID)
	}
	defer c.activeTurns.Delete(threadID)
	for {
		ev, ok := q.recv(ctx)
		if !ok {
			// queue closed (process died) before turn/completed
			if res.Status == "" {
				res.Status = "failed"
			}
			if res.Error == "" {
				res.Error = "app-server connection closed"
			}
			return res, nil
		}
		if onEvent != nil {
			onEvent(ev)
		}
		switch ev["method"] {
		case "item/agentMessage/delta":
			if d, ok := ev["delta"].(string); ok {
				res.Message += d
			}
		case "item/completed":
			if item, ok := ev["item"].(map[string]any); ok {
				if t, _ := item["type"].(string); t == "agentMessage" {
					if text, _ := item["text"].(string); text != "" {
						res.Message = text // authoritative final text
					}
				}
			}
		case "turn/completed":
			if turn, ok := ev["turn"].(map[string]any); ok {
				if s, _ := turn["status"].(string); s != "" {
					res.Status = s
				}
				if e, ok := turn["error"].(map[string]any); ok {
					if msg, _ := e["message"].(string); msg != "" {
						res.Error = msg
					}
				}
			}
			return res, nil
		}
	}
}

// childEnv builds the app-server process environment: the inherited
// environment with HOME/CODEX_HOME/RUST_LOG pinned, then any CODEX_API_ENV_*
// entries applied last so they can override the built-ins.
func childEnv(cfg Config) []string {
	env := map[string]string{}
	for _, kv := range os.Environ() {
		key, value, _ := strings.Cut(kv, "=")
		env[key] = value
	}
	if cfg.Home != "" {
		env["HOME"] = cfg.Home
	}
	if cfg.CodexHome != "" {
		env["CODEX_HOME"] = cfg.CodexHome
	}
	env["RUST_LOG"] = "off"
	for key, value := range cfg.ChildEnv {
		env[key] = value
	}
	out := make([]string, 0, len(env))
	for key, value := range env {
		out = append(out, key+"="+value)
	}
	return out
}

func parseID(raw json.RawMessage) (int64, bool) {
	s := strings.TrimSpace(string(raw))
	if s == "" {
		return 0, false
	}
	if n, err := strconv.ParseInt(s, 10, 64); err == nil {
		return n, true
	}
	return 0, false
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
