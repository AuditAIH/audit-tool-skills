// codex-app-server exposes the codex app-server JSON-RPC protocol behind a
// small HTTP API.
//
// POST <api_prefix>/messages {query, conversation_id?, app_id?, user_id?, cwd?, stream?}
// creates a codex thread (new conversation) or resumes an existing one, then
// starts a turn and returns the agent reply, either aggregated or streamed
// as SSE.
//
// All configuration comes from an env-style config file (default ./.env,
// override with -config or CODEX_API_CONFIG); real environment variables
// take precedence over file entries.
package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

type Config struct {
	ListenIP       string            // listen IP, e.g. "0.0.0.0"
	Port           string            // listen port, e.g. "5040"
	APIPrefix      string            // route prefix, e.g. "/api" -> POST /api/messages
	DBPath         string            // SQLite file path
	WorkspaceBase  string            // id-based workspaces: <base>/<app_id>/workspace/<user_id>
	WorkDir        string            // fixed cwd; empty = decided per request
	Bin            string            // codex CLI binary
	CodexHome      string            // CODEX_HOME for auth/session data
	Home           string            // HOME for the app-server process
	AuthToken      string            // optional API key (Bearer); empty = no auth
	LogLevel       string            // error | request | output
	ApprovalPolicy string            // never | onRequest | onFailure | unlessTrusted
	Sandbox        string            // dangerFullAccess | workspaceWrite | readOnly | externalSandbox
	Yolo           bool              // true = force dangerFullAccess + never (full unrestricted, for pre-sandboxed env like docker)
	Model          string            // optional model override; empty = configured default
	ChildEnv       map[string]string // CODEX_API_ENV_* entries injected into the child process
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envBool(key string) bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(key))) {
	case "1", "true", "yes", "on":
		return true
	}
	return false
}

// loadEnvFile reads a KEY=VALUE config file into the process environment.
// Existing environment variables win over file entries. A missing file is
// only an error when the path was given explicitly.
func loadEnvFile(path string, explicit bool) error {
	data, err := os.ReadFile(path)
	if err != nil {
		if explicit || !os.IsNotExist(err) {
			return err
		}
		return nil
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		value = strings.Trim(strings.TrimSpace(value), `"'`)
		if key == "" {
			continue
		}
		if _, exists := os.LookupEnv(key); !exists {
			os.Setenv(key, value)
		}
	}
	return nil
}

// collectChildEnv collects CODEX_API_ENV_* variables to inject into the
// app-server child process: CODEX_API_ENV_FOO=bar -> FOO=bar.
func collectChildEnv() map[string]string {
	out := map[string]string{}
	for _, kv := range os.Environ() {
		key, value, _ := strings.Cut(kv, "=")
		if name, ok := strings.CutPrefix(key, "CODEX_API_ENV_"); ok && name != "" {
			out[name] = value
		}
	}
	return out
}

func loadConfig() Config {
	home, _ := os.UserHomeDir()
	prefix := "/" + strings.Trim(envOr("CODEX_API_PREFIX", "api"), "/")
	return Config{
		ListenIP:       envOr("CODEX_API_LISTEN_IP", "0.0.0.0"),
		Port:           envOr("CODEX_API_PORT", "5040"),
		APIPrefix:      prefix,
		DBPath:         envOr("CODEX_API_DB", "./codex-app-server.db"),
		WorkspaceBase:  envOr("CODEX_API_WORKSPACE_BASE", "./home"),
		WorkDir:        os.Getenv("CODEX_API_WORK_DIR"),
		Bin:            envOr("CODEX_API_BIN", "codex"),
		CodexHome:      envOr("CODEX_API_CODEX_HOME", filepath.Join(home, ".codex")),
		Home:           envOr("CODEX_API_HOME", home),
		AuthToken:      os.Getenv("CODEX_API_AUTH_TOKEN"),
		LogLevel:       envOr("CODEX_API_LOG_LEVEL", "request"),
		ApprovalPolicy: envOr("CODEX_API_APPROVAL_POLICY", "never"),
		Sandbox:        envOr("CODEX_API_SANDBOX", "dangerFullAccess"),
		Yolo:           envBool("CODEX_API_YOLO"),
		Model:          os.Getenv("CODEX_API_MODEL"),
		ChildEnv:       collectChildEnv(),
	}
}

func main() {
	defaultPath := envOr("CODEX_API_CONFIG", ".env")
	configPath := flag.String("config", defaultPath, "env config file path")
	flag.Parse()
	explicit := *configPath != ".env" || os.Getenv("CODEX_API_CONFIG") != ""
	if err := loadEnvFile(*configPath, explicit); err != nil {
		log.Fatalf("load config: %v", err)
	}

	cfg := loadConfig()
	currentLevel = parseLogLevel(cfg.LogLevel)

	store, err := OpenStore(cfg.DBPath)
	if err != nil {
		log.Fatalf("open store: %v", err)
	}
	defer store.Close()

	if err := os.MkdirAll(cfg.WorkspaceBase, 0o755); err != nil {
		log.Fatalf("create workspace base: %v", err)
	}

	client := NewClient(cfg)
	defer client.Stop()
	if err := client.Start(context.Background()); err != nil {
		log.Fatalf("start app-server: %v", err)
	}

	addr := cfg.ListenIP + ":" + cfg.Port
	srv := NewServer(cfg, store, client)
	logRequestf("codex-app-server listening on %s (api prefix: %s, approval: %s, sandbox: %s, log level: %s)",
		addr, cfg.APIPrefix, cfg.ApprovalPolicy, cfg.Sandbox, cfg.LogLevel)
	log.Fatal(http.ListenAndServe(addr, srv.Handler()))
}
