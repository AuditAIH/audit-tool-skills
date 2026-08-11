package main

import (
	"database/sql"
	"errors"

	_ "modernc.org/sqlite"
)

// Conversation maps an API conversation to a codex app-server thread.
type Conversation struct {
	ConversationID string
	UserID         string
	ThreadID       string // codex thread id (empty until thread/start)
}

type Store struct {
	db *sql.DB
}

func OpenStore(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	_, err = db.Exec(`
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL,
  thread_id       TEXT NOT NULL DEFAULT ''
);`)
	if err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db}, nil
}

func (s *Store) Close() error { return s.db.Close() }

var ErrNotFound = errors.New("conversation not found")

func (s *Store) GetConversation(id string) (*Conversation, error) {
	var c Conversation
	err := s.db.QueryRow(
		`SELECT conversation_id, user_id, thread_id FROM conversations WHERE conversation_id = ?`, id,
	).Scan(&c.ConversationID, &c.UserID, &c.ThreadID)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &c, nil
}

func (s *Store) CreateConversation(id, userID string) error {
	_, err := s.db.Exec(
		`INSERT OR IGNORE INTO conversations (conversation_id, user_id) VALUES (?, ?)`,
		id, userID,
	)
	return err
}


func (s *Store) SetThreadID(id, threadID string) error {
	_, err := s.db.Exec(
		`UPDATE conversations SET thread_id = ? WHERE conversation_id = ?`,
		threadID, id,
	)
	return err
}

func (s *Store) GetConversationByThreadID(threadID string) (*Conversation, error) {
	var c Conversation
	err := s.db.QueryRow(
		`SELECT conversation_id, user_id, thread_id FROM conversations WHERE thread_id = ?`, threadID,
	).Scan(&c.ConversationID, &c.UserID, &c.ThreadID)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &c, nil
}

// DeleteConversation removes the conversation record by conversation_id.
func (s *Store) DeleteConversation(id string) error {
	_, err := s.db.Exec(`DELETE FROM conversations WHERE conversation_id = ?`, id)
	return err
}
