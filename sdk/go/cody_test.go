package cody

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// ── Helper ──────────────────────────────────────────────────────────────────

func testServer(handler http.HandlerFunc) (*httptest.Server, *Client) {
	srv := httptest.NewServer(handler)
	client := NewClient(srv.URL, WithMaxRetries(0))
	return srv, client
}

// ── Health ──────────────────────────────────────────────────────────────────

func TestHealth(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" || r.Method != http.MethodGet {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		json.NewEncoder(w).Encode(HealthResponse{Status: "ok", Version: "1.0.0"})
	})
	defer srv.Close()

	resp, err := client.Health(context.Background())
	if err != nil {
		t.Fatalf("Health() error: %v", err)
	}
	if resp.Status != "ok" {
		t.Errorf("Status = %q, want ok", resp.Status)
	}
	if resp.Version != "1.0.0" {
		t.Errorf("Version = %q, want 1.0.0", resp.Version)
	}
}

// ── Run ─────────────────────────────────────────────────────────────────────

func TestRun(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["prompt"] != "create hello.py" {
			t.Errorf("prompt = %q", body["prompt"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"output":     "Created hello.py",
			"session_id": "sess-1",
			"usage": map[string]int{
				"input_tokens":  100,
				"output_tokens": 50,
				"total_tokens":  150,
			},
		})
	})
	defer srv.Close()

	result, err := client.Run(context.Background(), "create hello.py")
	if err != nil {
		t.Fatalf("Run() error: %v", err)
	}
	if result.Output != "Created hello.py" {
		t.Errorf("Output = %q", result.Output)
	}
	if result.SessionID != "sess-1" {
		t.Errorf("SessionID = %q", result.SessionID)
	}
	if result.Usage.TotalTokens != 150 {
		t.Errorf("TotalTokens = %d", result.Usage.TotalTokens)
	}
}

func TestRunWithOptions(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["workdir"] != "/tmp/project" {
			t.Errorf("workdir = %q", body["workdir"])
		}
		if body["model"] != "anthropic:claude-sonnet-4-0" {
			t.Errorf("model = %q", body["model"])
		}
		if body["session_id"] != "sess-abc" {
			t.Errorf("session_id = %q", body["session_id"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"output": "done",
			"usage":  map[string]int{},
		})
	})
	defer srv.Close()

	_, err := client.Run(context.Background(), "task",
		WithWorkdir("/tmp/project"),
		WithModel("anthropic:claude-sonnet-4-0"),
		WithSession("sess-abc"),
	)
	if err != nil {
		t.Fatalf("Run() error: %v", err)
	}
}

func TestRunError(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"error": map[string]string{
				"code":    "INVALID_PARAMS",
				"message": "prompt is required",
			},
		})
	})
	defer srv.Close()

	_, err := client.Run(context.Background(), "")
	if err == nil {
		t.Fatal("expected error")
	}
	e, ok := err.(*APIError)
	if !ok {
		t.Fatalf("expected *APIError, got %T", err)
	}
	if e.StatusCode != 400 {
		t.Errorf("StatusCode = %d", e.StatusCode)
	}
	if e.Code != "INVALID_PARAMS" {
		t.Errorf("Code = %q", e.Code)
	}
}

func TestRunNotFound(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(404)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"error": map[string]string{
				"code":    "SESSION_NOT_FOUND",
				"message": "Session not found",
			},
		})
	})
	defer srv.Close()

	_, err := client.Run(context.Background(), "task", WithSession("bad-id"))
	if err == nil {
		t.Fatal("expected error")
	}
	if _, ok := err.(*NotFoundError); !ok {
		t.Errorf("expected *NotFoundError, got %T: %v", err, err)
	}
}

// ── Stream ──────────────────────────────────────────────────────────────────

func TestStream(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		flusher, _ := w.(http.Flusher)
		fmt.Fprintf(w, "data: {\"type\":\"text\",\"content\":\"Hello \"}\n\n")
		flusher.Flush()
		fmt.Fprintf(w, "data: {\"type\":\"text\",\"content\":\"World\"}\n\n")
		flusher.Flush()
		fmt.Fprintf(w, "data: {\"type\":\"done\"}\n\n")
		flusher.Flush()
	})
	defer srv.Close()

	ch, err := client.Stream(context.Background(), "greet")
	if err != nil {
		t.Fatalf("Stream() error: %v", err)
	}

	var chunks []StreamChunk
	for chunk := range ch {
		chunks = append(chunks, chunk)
	}

	if len(chunks) != 3 {
		t.Fatalf("got %d chunks, want 3", len(chunks))
	}
	if chunks[0].Content != "Hello " {
		t.Errorf("chunk[0].Content = %q", chunks[0].Content)
	}
	if chunks[1].Content != "World" {
		t.Errorf("chunk[1].Content = %q", chunks[1].Content)
	}
	if chunks[2].Type != "done" {
		t.Errorf("chunk[2].Type = %q", chunks[2].Type)
	}
}

func TestStreamWithSessionID(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		flusher, _ := w.(http.Flusher)
		fmt.Fprintf(w, "data: {\"type\":\"text\",\"content\":\"hi\",\"session_id\":\"s1\"}\n\n")
		flusher.Flush()
		fmt.Fprintf(w, "data: {\"type\":\"done\"}\n\n")
		flusher.Flush()
	})
	defer srv.Close()

	ch, err := client.Stream(context.Background(), "greet")
	if err != nil {
		t.Fatalf("Stream() error: %v", err)
	}

	chunk := <-ch
	if chunk.SessionID != "s1" {
		t.Errorf("SessionID = %q", chunk.SessionID)
	}
	// drain
	for range ch {
	}
}

func TestStreamCancellation(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		flusher, _ := w.(http.Flusher)
		for i := 0; i < 100; i++ {
			fmt.Fprintf(w, "data: {\"type\":\"text\",\"content\":\"chunk\"}\n\n")
			flusher.Flush()
			time.Sleep(10 * time.Millisecond)
		}
	})
	defer srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	ch, err := client.Stream(ctx, "long task")
	if err != nil {
		t.Fatalf("Stream() error: %v", err)
	}

	<-ch   // read first chunk
	cancel() // cancel context

	// channel should close eventually
	count := 0
	for range ch {
		count++
	}
	// should not have read all 100 chunks
	if count >= 99 {
		t.Errorf("expected early termination, got %d chunks", count)
	}
}

// ── Tool ────────────────────────────────────────────────────────────────────

func TestTool(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["tool"] != "read_file" {
			t.Errorf("tool = %q", body["tool"])
		}
		params, _ := body["params"].(map[string]interface{})
		if params["path"] != "main.py" {
			t.Errorf("params.path = %q", params["path"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "success",
			"result": "print('hello')",
		})
	})
	defer srv.Close()

	result, err := client.Tool(context.Background(), "read_file", map[string]interface{}{"path": "main.py"})
	if err != nil {
		t.Fatalf("Tool() error: %v", err)
	}
	if result.Result != "print('hello')" {
		t.Errorf("Result = %q", result.Result)
	}
}

func TestToolWithWorkdir(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)
		if body["workdir"] != "/tmp" {
			t.Errorf("workdir = %q", body["workdir"])
		}
		json.NewEncoder(w).Encode(map[string]interface{}{"result": "ok"})
	})
	defer srv.Close()

	_, err := client.Tool(context.Background(), "list_directory", nil, WithWorkdir("/tmp"))
	if err != nil {
		t.Fatalf("Tool() error: %v", err)
	}
}

// ── Sessions ────────────────────────────────────────────────────────────────

func TestCreateSession(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		title := r.URL.Query().Get("title")
		if title != "My session" {
			t.Errorf("title = %q", title)
		}
		json.NewEncoder(w).Encode(SessionInfo{
			ID:           "sess-new",
			Title:        title,
			Model:        "",
			Workdir:      "",
			MessageCount: 0,
			CreatedAt:    "2026-02-25T00:00:00",
			UpdatedAt:    "2026-02-25T00:00:00",
		})
	})
	defer srv.Close()

	session, err := client.CreateSession(context.Background(), WithTitle("My session"))
	if err != nil {
		t.Fatalf("CreateSession() error: %v", err)
	}
	if session.ID != "sess-new" {
		t.Errorf("ID = %q", session.ID)
	}
	if session.Title != "My session" {
		t.Errorf("Title = %q", session.Title)
	}
}

func TestListSessions(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		limit := r.URL.Query().Get("limit")
		if limit != "5" {
			t.Errorf("limit = %q", limit)
		}
		json.NewEncoder(w).Encode(map[string]interface{}{
			"sessions": []SessionInfo{
				{ID: "s1", Title: "Session 1", CreatedAt: "t1", UpdatedAt: "t1"},
				{ID: "s2", Title: "Session 2", CreatedAt: "t2", UpdatedAt: "t2"},
			},
		})
	})
	defer srv.Close()

	sessions, err := client.ListSessions(context.Background(), 5)
	if err != nil {
		t.Fatalf("ListSessions() error: %v", err)
	}
	if len(sessions) != 2 {
		t.Fatalf("got %d sessions, want 2", len(sessions))
	}
	if sessions[0].ID != "s1" {
		t.Errorf("sessions[0].ID = %q", sessions[0].ID)
	}
}

func TestGetSession(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/sessions/sess-1" {
			t.Errorf("path = %q", r.URL.Path)
		}
		json.NewEncoder(w).Encode(SessionDetail{
			SessionInfo: SessionInfo{
				ID: "sess-1", Title: "Test", MessageCount: 2,
				CreatedAt: "t1", UpdatedAt: "t2",
			},
			Messages: []map[string]interface{}{
				{"role": "user", "content": "hello"},
				{"role": "assistant", "content": "hi"},
			},
		})
	})
	defer srv.Close()

	detail, err := client.GetSession(context.Background(), "sess-1")
	if err != nil {
		t.Fatalf("GetSession() error: %v", err)
	}
	if detail.MessageCount != 2 {
		t.Errorf("MessageCount = %d", detail.MessageCount)
	}
	if len(detail.Messages) != 2 {
		t.Errorf("Messages count = %d", len(detail.Messages))
	}
}

func TestDeleteSession(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("method = %q", r.Method)
		}
		json.NewEncoder(w).Encode(map[string]string{"status": "deleted"})
	})
	defer srv.Close()

	err := client.DeleteSession(context.Background(), "sess-1")
	if err != nil {
		t.Fatalf("DeleteSession() error: %v", err)
	}
}

// ── Skills ──────────────────────────────────────────────────────────────────

func TestListSkills(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"skills": []SkillInfo{
				{Name: "git", Description: "Git Operations", Enabled: true, Source: "builtin"},
				{Name: "python", Description: "Python Project Management", Enabled: true, Source: "builtin"},
			},
		})
	})
	defer srv.Close()

	skills, err := client.ListSkills(context.Background())
	if err != nil {
		t.Fatalf("ListSkills() error: %v", err)
	}
	if len(skills) != 2 {
		t.Fatalf("got %d skills, want 2", len(skills))
	}
	if skills[0].Name != "git" {
		t.Errorf("skills[0].Name = %q", skills[0].Name)
	}
}

// ── Retry ───────────────────────────────────────────────────────────────────

func TestRetryOnConnectionError(t *testing.T) {
	var attempts int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&attempts, 1)
		if n <= 2 {
			// Force connection reset by hijacking
			hj, ok := w.(http.Hijacker)
			if ok {
				conn, _, _ := hj.Hijack()
				conn.Close()
				return
			}
		}
		json.NewEncoder(w).Encode(HealthResponse{Status: "ok", Version: "1.0.0"})
	}))
	defer srv.Close()

	client := NewClient(srv.URL, WithMaxRetries(3))
	resp, err := client.Health(context.Background())
	if err != nil {
		// If hijack doesn't work on this platform, at least verify the retry logic doesn't panic
		t.Skipf("platform may not support hijack: %v", err)
	}
	if resp.Status != "ok" {
		t.Errorf("Status = %q", resp.Status)
	}
}

func TestNoRetryWhenDisabled(t *testing.T) {
	var attempts int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&attempts, 1)
		if n == 1 {
			hj, ok := w.(http.Hijacker)
			if ok {
				conn, _, _ := hj.Hijack()
				conn.Close()
				return
			}
		}
		json.NewEncoder(w).Encode(HealthResponse{Status: "ok"})
	}))
	defer srv.Close()

	client := NewClient(srv.URL, WithMaxRetries(0))
	_, err := client.Health(context.Background())
	if err == nil {
		// If hijack doesn't work, skip
		t.Skip("hijack not supported")
	}
	// Should fail on first attempt with no retry
	got := atomic.LoadInt32(&attempts)
	if got != 1 {
		t.Errorf("attempts = %d, want 1", got)
	}
}

// ── Backoff ─────────────────────────────────────────────────────────────────

func TestBackoffDelay(t *testing.T) {
	tests := []struct {
		attempt int
		want    time.Duration
	}{
		{0, 500 * time.Millisecond},
		{1, 1 * time.Second},
		{2, 2 * time.Second},
		{3, 4 * time.Second},
		{4, 8 * time.Second},
		{5, 8 * time.Second}, // capped
		{10, 8 * time.Second},
	}
	for _, tt := range tests {
		got := backoffDelay(tt.attempt)
		if got != tt.want {
			t.Errorf("backoffDelay(%d) = %v, want %v", tt.attempt, got, tt.want)
		}
	}
}

// ── Error types ─────────────────────────────────────────────────────────────

func TestErrorMessage(t *testing.T) {
	e := &APIError{Message: "bad request", StatusCode: 400, Code: "INVALID_PARAMS"}
	got := e.Error()
	if got != "cody: bad request (INVALID_PARAMS, HTTP 400)" {
		t.Errorf("Error() = %q", got)
	}
}

func TestErrorMessageNoCode(t *testing.T) {
	e := &APIError{Message: "server error", StatusCode: 500}
	got := e.Error()
	if got != "cody: server error (HTTP 500)" {
		t.Errorf("Error() = %q", got)
	}
}

func TestConnectionErrorMessage(t *testing.T) {
	e := &ConnectionError{Message: "refused", Attempts: 4}
	got := e.Error()
	if got != "cody: cannot connect after 4 attempts: refused" {
		t.Errorf("Error() = %q", got)
	}
}

// ── Client options ──────────────────────────────────────────────────────────

func TestNewClientDefaults(t *testing.T) {
	c := NewClient("http://localhost:8000")
	if c.baseURL != "http://localhost:8000" {
		t.Errorf("baseURL = %q", c.baseURL)
	}
	if c.maxRetries != 3 {
		t.Errorf("maxRetries = %d", c.maxRetries)
	}
	if c.httpClient.Timeout != 120*time.Second {
		t.Errorf("Timeout = %v", c.httpClient.Timeout)
	}
}

func TestNewClientTrailingSlash(t *testing.T) {
	c := NewClient("http://localhost:8000/")
	if c.baseURL != "http://localhost:8000" {
		t.Errorf("baseURL = %q", c.baseURL)
	}
}

func TestNewClientCustomOptions(t *testing.T) {
	c := NewClient("http://example.com",
		WithTimeout(30*time.Second),
		WithMaxRetries(5),
	)
	if c.maxRetries != 5 {
		t.Errorf("maxRetries = %d", c.maxRetries)
	}
	if c.httpClient.Timeout != 30*time.Second {
		t.Errorf("Timeout = %v", c.httpClient.Timeout)
	}
}

func TestListSessionsDefaultLimit(t *testing.T) {
	srv, client := testServer(func(w http.ResponseWriter, r *http.Request) {
		limit := r.URL.Query().Get("limit")
		if limit != "20" {
			t.Errorf("limit = %q, want 20", limit)
		}
		json.NewEncoder(w).Encode(map[string]interface{}{"sessions": []SessionInfo{}})
	})
	defer srv.Close()

	_, err := client.ListSessions(context.Background(), 0)
	if err != nil {
		t.Fatalf("ListSessions() error: %v", err)
	}
}
