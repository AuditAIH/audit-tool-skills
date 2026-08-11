package main

import (
	"crypto/md5"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// MessageRequest is the body of POST <prefix>/messages.
type MessageRequest struct {
	Query          string `json:"query"`
	AppID          string `json:"app_id"`
	ConversationID string `json:"conversation_id"`
	UserID         string `json:"user_id"`
	Cwd            string `json:"cwd"`   // explicit working directory for the thread
	Stream         bool   `json:"stream"`
}

// MessageResponse is the non-streaming response.
type MessageResponse struct {
	ConversationID string `json:"conversation_id"`
	ThreadID       string `json:"thread_id"`
	TurnID         string `json:"turn_id"`
	Message        string `json:"message"`
	Status         string `json:"status"`
	Error          string `json:"error,omitempty"`
}

// TerminateResponse is returned for an empty-query abort request.
type TerminateResponse struct {
	ConversationID string `json:"conversation_id"`
	ThreadID       string `json:"thread_id,omitempty"`
	TurnID         string `json:"turn_id,omitempty"`
	Status         string `json:"status"`
	Message        string `json:"message"`
}

// ids double as path components, so keep them filesystem-safe.
var idPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`)

// defaultOwner owns conversations created without a user_id.
const defaultOwner = "every"

// newConversationID returns a random RFC 4122 version 4 UUID.
func newConversationID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

type Server struct {
	cfg    Config
	store  *Store
	client *Client
	// per-conversation locks keep concurrent requests for the same
	// conversation from interleaving turn/start calls
	locks sync.Map // map[string]*sync.Mutex
}

func NewServer(cfg Config, store *Store, client *Client) *Server {
	return &Server{cfg: cfg, store: store, client: client}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("POST "+s.cfg.APIPrefix+"/messages", s.auth(s.handleMessage))
	mux.HandleFunc("DELETE "+s.cfg.APIPrefix+"/conversations", s.auth(s.handleDelete))
	mux.HandleFunc("POST "+s.cfg.APIPrefix+"/upload", s.auth(s.handleUpload))
	return requestLogging(mux)
}

// statusRecorder captures the response status for access logging.
type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

// Flush forwards to the underlying Flusher so SSE keeps working
// through the recorder.
func (r *statusRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func requestLogging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		logRequestf("%s %s -> %d (%s)", r.Method, r.URL.Path, rec.status, time.Since(start).Round(time.Millisecond))
	})
}

func (s *Server) auth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.AuthToken != "" && r.Header.Get("Authorization") != "Bearer "+s.cfg.AuthToken {
			writeError(w, http.StatusUnauthorized, "invalid or missing bearer token")
			return
		}
		next(w, r)
	}
}

func (s *Server) conversationLock(id string) *sync.Mutex {
	mu, _ := s.locks.LoadOrStore(id, &sync.Mutex{})
	return mu.(*sync.Mutex)
}

// handleTerminate aborts the active turn (if any) on the conversation
// identified by req.ConversationID. It writes an English JSON response
// describing the outcome and never starts a new turn.
func (s *Server) handleTerminate(w http.ResponseWriter, r *http.Request, req *MessageRequest) {
	userID := req.UserID
	if userID == "" {
		userID = defaultOwner
	}
	conv, err := s.store.GetConversation(req.ConversationID)
	if errors.Is(err, ErrNotFound) {
		writeJSON(w, http.StatusOK, TerminateResponse{
			ConversationID: req.ConversationID,
			Status:         "no_conversation",
			Message:        "conversation not found",
		})
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "load conversation: "+err.Error())
		return
	}
	if conv.UserID != userID {
		writeError(w, http.StatusForbidden, "you are not allowed to access this conversation, please start a new one")
		return
	}
	if conv.ThreadID == "" {
		writeJSON(w, http.StatusOK, TerminateResponse{
			ConversationID: conv.ConversationID,
			Status:         "no_active_turn",
			Message:        "no active turn to terminate",
		})
		return
	}
	turnID, interrupted, err := s.client.Interrupt(r.Context(), conv.ThreadID)
	if err != nil {
		logRequestf("terminate failed conversation=%s: %v", conv.ConversationID, err)
		writeJSON(w, http.StatusOK, TerminateResponse{
			ConversationID: conv.ConversationID,
			Status:         "no_active_turn",
			Message:        "no active turn to terminate",
		})
		return
	}
	if !interrupted {
		writeJSON(w, http.StatusOK, TerminateResponse{
			ConversationID: conv.ConversationID,
			Status:         "no_active_turn",
			Message:        "no active turn to terminate",
		})
		return
	}
	logRequestf("terminate conversation=%s thread=%s turn=%s", conv.ConversationID, conv.ThreadID, turnID)
	writeJSON(w, http.StatusOK, TerminateResponse{
		ConversationID: conv.ConversationID,
		ThreadID:       conv.ThreadID,
		TurnID:         turnID,
		Status:         "terminated",
		Message:        "conversation manually terminated",
	})
}

// trySteer attempts to insert query into an active in-flight turn on the
// conversation's thread. It writes the response and returns true when the
// input was steered; returns false (no response written) when there is no
// active turn, so the caller can fall back to starting a new turn.
func (s *Server) trySteer(w http.ResponseWriter, r *http.Request, conv *Conversation, query string) bool {
	if conv.ThreadID == "" {
		return false
	}
	turnID, steered, err := s.client.Steer(r.Context(), conv.ThreadID, query)
	if err != nil {
		logRequestf("steer failed conversation=%s, falling back to new turn: %v", conv.ConversationID, err)
		return false
	}
	if !steered {
		return false
	}
	logRequestf("steer conversation=%s thread=%s turn=%s", conv.ConversationID, conv.ThreadID, turnID)
	writeJSON(w, http.StatusOK, MessageResponse{
		ConversationID: conv.ConversationID,
		ThreadID:       conv.ThreadID,
		TurnID:         turnID,
		Status:         "steered",
	})
	return true
}

func (s *Server) handleMessage(w http.ResponseWriter, r *http.Request) {
	var req MessageRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.AppID != "" && !idPattern.MatchString(req.AppID) {
		writeError(w, http.StatusBadRequest, "app_id must match "+idPattern.String())
		return
	}
	if req.UserID != "" && !idPattern.MatchString(req.UserID) {
		writeError(w, http.StatusBadRequest, "user_id must match "+idPattern.String())
		return
	}
	// Empty query with a conversation_id terminates the active turn on that
	// conversation (manual abort).
	if req.Query == "" {
		if req.ConversationID == "" {
			writeError(w, http.StatusBadRequest, "query is required, or provide conversation_id to terminate")
			return
		}
		if !idPattern.MatchString(req.ConversationID) {
			writeError(w, http.StatusBadRequest, "conversation_id must match "+idPattern.String())
			return
		}
		s.handleTerminate(w, r, &req)
		return
	}
	if req.ConversationID == "" {
		req.ConversationID = newConversationID()
	} else if !idPattern.MatchString(req.ConversationID) {
		writeError(w, http.StatusBadRequest, "conversation_id must match "+idPattern.String())
		return
	}

	cwd := s.resolveCwd(&req)
	// Ensure the workspace directory exists so codex can spawn shell
	// processes with it as cwd. Without this, process creation fails
	// with ENOENT ("No such file or directory").
	if cwd != "" && cwd != "." {
		if err := os.MkdirAll(cwd, 0o755); err != nil {
			writeError(w, http.StatusInternalServerError, "create workspace dir: "+err.Error())
			return
		}
	}
	userID := req.UserID
	if userID == "" {
		userID = defaultOwner
	}

	// Resolve (or create) the conversation record outside the turn lock so a
	// steer can run concurrently with an active turn. Re-fetch after create to
	// pick up the canonical owner in case a concurrent request created it.
	conv, err := s.store.GetConversation(req.ConversationID)
	if errors.Is(err, ErrNotFound) {
		if err := s.store.CreateConversation(req.ConversationID, userID); err != nil {
			writeError(w, http.StatusInternalServerError, "create conversation: "+err.Error())
			return
		}
		conv, err = s.store.GetConversation(req.ConversationID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "load conversation: "+err.Error())
			return
		}
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "load conversation: "+err.Error())
		return
	}
	if conv.UserID != userID {
		writeError(w, http.StatusForbidden, "you are not allowed to access this conversation, please start a new one")
		return
	}

	// Steer: if a turn is still running on this thread, insert the input into
	// it (natural Codex "type while it works"). Done outside the lock so it
	// isn't blocked by the running turn.
	if s.trySteer(w, r, conv, req.Query) {
		return
	}

	// No active turn: start a new turn. The lock serializes thread creation
	// and turn start for this conversation.
	mu := s.conversationLock(req.ConversationID)
	mu.Lock()
	defer mu.Unlock()

	// Re-check steer after acquiring the lock: a turn may have started
	// between the check above and here.
	if s.trySteer(w, r, conv, req.Query) {
		return
	}

	// Create/resume the thread and start a new turn.
	if conv.ThreadID == "" {
		threadID, err := s.client.StartThread(r.Context(), cwd)
		if err != nil {
			logErrorf("thread/start failed conversation=%s: %v", conv.ConversationID, err)
			writeError(w, http.StatusInternalServerError, "create thread: "+err.Error())
			return
		}
		if err := s.store.SetThreadID(conv.ConversationID, threadID); err != nil {
			logErrorf("persist thread id: %v", err)
		}
		conv.ThreadID = threadID
		logRequestf("thread start conversation=%s thread=%s cwd=%s", conv.ConversationID, threadID, cwd)
	} else {
		if err := s.client.ResumeThread(r.Context(), conv.ThreadID); err != nil {
			logErrorf("thread/resume failed conversation=%s: %v", conv.ConversationID, err)
			writeError(w, http.StatusInternalServerError, "resume thread: "+err.Error())
			return
		}
		logRequestf("thread resume conversation=%s thread=%s", conv.ConversationID, conv.ThreadID)
	}

	if req.Stream {
		s.runStreaming(w, r, conv, req.Query)
		return
	}
	s.runSync(w, r, conv, req.Query)
}

// resolveCwd picks the working directory for a thread. Precedence:
//
//  1. cwd passed in the request (highest)
//  2. app_id / user_id: <workspace_base>[/<app_id>]/workspace[/<user_id>]
//  3. work_dir from the config file
//  4. the process working directory
// resolveWorkDir picks the working directory from explicit cwd, app_id/user_id
// derivation, configured work dir, or the process cwd (in that order).
func (s *Server) resolveWorkDir(cwd, appID, userID string) string {
	if cwd != "" {
		return cwd
	}
	if appID != "" || userID != "" {
		parts := []string{s.cfg.WorkspaceBase}
		if appID != "" {
			parts = append(parts, appID)
		}
		parts = append(parts, "workspace")
		if userID != "" {
			parts = append(parts, userID)
		}
		return filepath.Join(parts...)
	}
	if s.cfg.WorkDir != "" {
		return s.cfg.WorkDir
	}
	if wd, err := os.Getwd(); err == nil {
		return wd
	}
	return "."
}

func (s *Server) resolveCwd(req *MessageRequest) string {
	return s.resolveWorkDir(req.Cwd, req.AppID, req.UserID)
}

func (s *Server) runSync(w http.ResponseWriter, r *http.Request, conv *Conversation, query string) {
	res, err := s.client.RunTurn(r.Context(), conv.ThreadID, query, nil)
	if err != nil {
		logErrorf("turn failed conversation=%s: %v", conv.ConversationID, err)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	logRequestf("turn done conversation=%s thread=%s turn=%s status=%s",
		conv.ConversationID, conv.ThreadID, res.TurnID, res.Status)
	writeJSON(w, http.StatusOK, MessageResponse{
		ConversationID: conv.ConversationID,
		ThreadID:       conv.ThreadID,
		TurnID:         res.TurnID,
		Message:        res.Message,
		Status:         res.Status,
		Error:          res.Error,
	})
}

// runStreaming forwards each notification as an SSE data frame, then
// terminates with a synthetic done event carrying the turn summary.
func (s *Server) runStreaming(w http.ResponseWriter, r *http.Request, conv *Conversation, query string) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming unsupported")
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)

	send := func(v any) {
		data, _ := json.Marshal(v)
		fmt.Fprintf(w, "data: %s\n\n", data)
		flusher.Flush()
	}

	res, err := s.client.RunTurn(r.Context(), conv.ThreadID, query, func(ev map[string]any) {
		send(ev)
	})
	if err != nil {
		logErrorf("turn failed conversation=%s: %v", conv.ConversationID, err)
		send(map[string]any{"method": "error", "error": err.Error()})
		return
	}
	logRequestf("turn done conversation=%s thread=%s turn=%s status=%s",
		conv.ConversationID, conv.ThreadID, res.TurnID, res.Status)
	send(map[string]any{
		"method":          "done",
		"conversation_id": conv.ConversationID,
		"thread_id":       conv.ThreadID,
		"turn_id":         res.TurnID,
		"message":         res.Message,
		"status":          res.Status,
		"error":           res.Error,
	})
}


// DeleteRequest is the body of DELETE <prefix>/conversations. Either
// conversation_id or thread_id identifies the conversation to delete.
type DeleteRequest struct {
	ConversationID string `json:"conversation_id"`
	ThreadID       string `json:"thread_id"`
	UserID         string `json:"user_id"`
}

// UploadResponse is returned by POST <prefix>/upload.
type UploadResponse struct {
	Path     string `json:"path"`
	Filename string `json:"filename"`
	MD5      string `json:"md5"`
	Size     int    `json:"size"`
	Original string `json:"original"`
}

// handleDelete permanently deletes a conversation/thread. Either
// conversation_id or thread_id may be supplied; user_id is used for ownership
// when a stored conversation record exists.
func (s *Server) handleDelete(w http.ResponseWriter, r *http.Request) {
	var req DeleteRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.ConversationID == "" && req.ThreadID == "" {
		writeError(w, http.StatusBadRequest, "conversation_id or thread_id is required")
		return
	}
	if req.ConversationID != "" && !idPattern.MatchString(req.ConversationID) {
		writeError(w, http.StatusBadRequest, "conversation_id must match "+idPattern.String())
		return
	}
	if req.ThreadID != "" && !idPattern.MatchString(req.ThreadID) {
		writeError(w, http.StatusBadRequest, "thread_id must match "+idPattern.String())
		return
	}
	userID := req.UserID
	if userID == "" {
		userID = defaultOwner
	}

	// Resolve the stored conversation (if any) by conversation_id or thread_id.
	var conv *Conversation
	var err error
	if req.ConversationID != "" {
		conv, err = s.store.GetConversation(req.ConversationID)
	} else {
		conv, err = s.store.GetConversationByThreadID(req.ThreadID)
	}
	if err != nil && !errors.Is(err, ErrNotFound) {
		writeError(w, http.StatusInternalServerError, "load conversation: "+err.Error())
		return
	}
	if conv != nil && conv.UserID != userID {
		writeError(w, http.StatusForbidden, "you are not allowed to access this conversation, please start a new one")
		return
	}

	threadID := req.ThreadID
	if threadID == "" && conv != nil {
		threadID = conv.ThreadID
	}
	convID := req.ConversationID
	if conv != nil {
		convID = conv.ConversationID
	}

	if threadID == "" && conv == nil {
		writeJSON(w, http.StatusOK, TerminateResponse{
			ConversationID: convID,
			Status:         "no_conversation",
			Message:        "conversation not found",
		})
		return
	}

	// Interrupt any active turn on the thread before deleting it.
	if threadID != "" {
		if _, _, ierr := s.client.Interrupt(r.Context(), threadID); ierr != nil {
			logRequestf("delete: interrupt failed thread=%s: %v", threadID, ierr)
		}
		if err := s.client.DeleteThread(r.Context(), threadID); err != nil {
			writeError(w, http.StatusInternalServerError, "delete thread: "+err.Error())
			return
		}
	}
	if conv != nil {
		if err := s.store.DeleteConversation(conv.ConversationID); err != nil {
			logErrorf("delete conversation record: %v", err)
		}
	}
	logRequestf("delete conversation=%s thread=%s", convID, threadID)
	writeJSON(w, http.StatusOK, TerminateResponse{
		ConversationID: convID,
		ThreadID:       threadID,
		Status:         "deleted",
		Message:        "conversation deleted",
	})
}

// handleUpload receives a single file (multipart "file" field), renames it to
// <md5><original-extension>, writes it into <workdir>/uploads/ (overwriting any
// existing file), and returns the absolute path.
func (s *Server) handleUpload(w http.ResponseWriter, r *http.Request) {
	const maxSize = 200 << 20 // 200 MB
	r.Body = http.MaxBytesReader(w, r.Body, maxSize)
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart upload: "+err.Error())
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "file field is required")
		return
	}
	defer file.Close()

	workDir := s.resolveWorkDir(r.FormValue("cwd"), r.FormValue("app_id"), r.FormValue("user_id"))
	data, err := io.ReadAll(file)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "read upload: "+err.Error())
		return
	}
	sum := md5.Sum(data)
	md5hex := hex.EncodeToString(sum[:])
	ext := filepath.Ext(header.Filename)
	uploadDir := filepath.Join(workDir, "uploads")
	if err := os.MkdirAll(uploadDir, 0o755); err != nil {
		writeError(w, http.StatusInternalServerError, "create upload dir: "+err.Error())
		return
	}
	name := md5hex + ext
	target := filepath.Join(uploadDir, name)
	if err := os.WriteFile(target, data, 0o644); err != nil {
		writeError(w, http.StatusInternalServerError, "write upload: "+err.Error())
		return
	}
	abs, err := filepath.Abs(target)
	if err != nil {
		abs = target
	}
	logRequestf("upload file=%s size=%d -> %s", header.Filename, len(data), abs)
	writeJSON(w, http.StatusOK, UploadResponse{
		Path:     abs,
		Filename: name,
		MD5:      md5hex,
		Size:     len(data),
		Original: header.Filename,
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	msg = strings.TrimSpace(msg)
	writeJSON(w, status, map[string]string{"error": msg})
}
