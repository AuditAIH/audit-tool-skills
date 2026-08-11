package main

import "log"

// LogLevel controls log verbosity. Levels are cumulative:
// output includes request, request includes error.
type LogLevel int

const (
	LevelError   LogLevel = iota // only failures
	LevelRequest                 // + run start/done and HTTP access lines
	LevelOutput                  // + every app-server notification line
)

var currentLevel = LevelRequest

func parseLogLevel(s string) LogLevel {
	switch s {
	case "error":
		return LevelError
	case "request":
		return LevelRequest
	case "output":
		return LevelOutput
	default:
		return LevelRequest
	}
}

func logErrorf(format string, args ...any) {
	if currentLevel >= LevelError {
		log.Printf("[ERROR] "+format, args...)
	}
}

func logRequestf(format string, args ...any) {
	if currentLevel >= LevelRequest {
		log.Printf("[REQUEST] "+format, args...)
	}
}

func logOutputf(format string, args ...any) {
	if currentLevel >= LevelOutput {
		log.Printf("[OUTPUT] "+format, args...)
	}
}
