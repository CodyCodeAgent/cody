// Package cody provides a Go client for the Cody RPC Server.
//
// Basic usage:
//
//	client := cody.NewClient("http://localhost:8000")
//
//	// One-shot
//	result, err := client.Run(ctx, "create hello.py")
//
//	// Multi-turn session
//	session, _ := client.CreateSession(ctx, nil)
//	client.Run(ctx, "create Flask app", cody.WithSession(session.ID))
//
//	// Streaming
//	ch, _ := client.Stream(ctx, "explain this code")
//	for chunk := range ch {
//	    fmt.Print(chunk.Content)
//	}
package cody

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// ── Response types ──────────────────────────────────────────────────────────

// Usage contains token usage information.
type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
	TotalTokens  int `json:"total_tokens"`
}

// RunResult is the response from Client.Run.
type RunResult struct {
	Output    string  `json:"output"`
	SessionID string  `json:"session_id,omitempty"`
	Usage     Usage   `json:"usage"`
}

// StreamChunk is a single chunk from a streaming response.
type StreamChunk struct {
	Type      string `json:"type"` // "text", "done", "error"
	Content   string `json:"content,omitempty"`
	SessionID string `json:"session_id,omitempty"`
}

// SessionInfo contains session metadata.
type SessionInfo struct {
	ID           string `json:"id"`
	Title        string `json:"title"`
	Model        string `json:"model"`
	Workdir      string `json:"workdir"`
	MessageCount int    `json:"message_count"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

// SessionDetail extends SessionInfo with message history.
type SessionDetail struct {
	SessionInfo
	Messages []map[string]interface{} `json:"messages"`
}

// ToolResult is the response from Client.Tool.
type ToolResult struct {
	Result string `json:"result"`
}

// SkillInfo contains skill metadata.
type SkillInfo struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Enabled     bool   `json:"enabled"`
	Source      string `json:"source"`
}

// HealthResponse is the response from Client.Health.
type HealthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

// ── Errors ──────────────────────────────────────────────────────────────────

// APIError is the base error type for the Cody SDK.
type APIError struct {
	Message    string
	StatusCode int
	Code       string // Structured error code (e.g. "TOOL_NOT_FOUND")
}

func (e *APIError) Error() string {
	if e.Code != "" {
		return fmt.Sprintf("cody: %s (%s, HTTP %d)", e.Message, e.Code, e.StatusCode)
	}
	return fmt.Sprintf("cody: %s (HTTP %d)", e.Message, e.StatusCode)
}

// ConnectionError indicates the server is unreachable after retries.
type ConnectionError struct {
	Message  string
	Attempts int
	Cause    error
}

func (e *ConnectionError) Error() string {
	return fmt.Sprintf("cody: cannot connect after %d attempts: %s", e.Attempts, e.Message)
}

func (e *ConnectionError) Unwrap() error { return e.Cause }

// NotFoundError indicates a 404 response.
type NotFoundError struct{ APIError }

// ── Options ─────────────────────────────────────────────────────────────────

// RunOption configures a Run or Stream call.
type RunOption func(*runOptions)

type runOptions struct {
	Workdir   string
	Model     string
	SessionID *string // pointer to distinguish unset from empty
}

// WithWorkdir sets the working directory for the request.
func WithWorkdir(dir string) RunOption {
	return func(o *runOptions) { o.Workdir = dir }
}

// WithModel sets the model for the request.
func WithModel(model string) RunOption {
	return func(o *runOptions) { o.Model = model }
}

// WithSession sets the session ID for multi-turn conversations.
func WithSession(id string) RunOption {
	return func(o *runOptions) { o.SessionID = &id }
}

// CreateSessionOption configures a CreateSession call.
type CreateSessionOption func(*createSessionOptions)

type createSessionOptions struct {
	Title   string
	Model   string
	Workdir string
}

// WithTitle sets the session title.
func WithTitle(title string) CreateSessionOption {
	return func(o *createSessionOptions) { o.Title = title }
}

// WithSessionModel sets the session default model.
func WithSessionModel(model string) CreateSessionOption {
	return func(o *createSessionOptions) { o.Model = model }
}

// WithSessionWorkdir sets the session working directory.
func WithSessionWorkdir(dir string) CreateSessionOption {
	return func(o *createSessionOptions) { o.Workdir = dir }
}

// ── Client ──────────────────────────────────────────────────────────────────

// Client is a Go client for the Cody RPC Server.
type Client struct {
	baseURL    string
	httpClient *http.Client
	maxRetries int
}

// ClientOption configures the Client.
type ClientOption func(*Client)

// WithTimeout sets the HTTP request timeout (default: 120s).
func WithTimeout(d time.Duration) ClientOption {
	return func(c *Client) { c.httpClient.Timeout = d }
}

// WithMaxRetries sets the max retry count on transient failures (default: 3).
func WithMaxRetries(n int) ClientOption {
	return func(c *Client) { c.maxRetries = n }
}

// WithHTTPClient sets a custom http.Client.
func WithHTTPClient(hc *http.Client) ClientOption {
	return func(c *Client) { c.httpClient = hc }
}

// NewClient creates a new Cody client.
func NewClient(baseURL string, opts ...ClientOption) *Client {
	c := &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		httpClient: &http.Client{Timeout: 120 * time.Second},
		maxRetries: 3,
	}
	for _, opt := range opts {
		opt(c)
	}
	return c
}

// ── Internal helpers ────────────────────────────────────────────────────────

func backoffDelay(attempt int) time.Duration {
	delay := 0.5 * math.Pow(2, float64(attempt))
	if delay > 8.0 {
		delay = 8.0
	}
	return time.Duration(delay * float64(time.Second))
}

func isRetryable(err error) bool {
	// Retry on connection refused, timeout, and temporary network errors
	if err == nil {
		return false
	}
	// net/http wraps errors — check common patterns
	msg := err.Error()
	return strings.Contains(msg, "connection refused") ||
		strings.Contains(msg, "connect:") ||
		strings.Contains(msg, "i/o timeout") ||
		strings.Contains(msg, "Client.Timeout") ||
		strings.Contains(msg, "EOF")
}

func (c *Client) doWithRetry(ctx context.Context, req *http.Request) (*http.Response, error) {
	var lastErr error
	for attempt := 0; attempt <= c.maxRetries; attempt++ {
		reqCopy := req.Clone(ctx)
		resp, err := c.httpClient.Do(reqCopy)
		if err != nil {
			lastErr = err
			if isRetryable(err) && attempt < c.maxRetries {
				select {
				case <-ctx.Done():
					return nil, ctx.Err()
				case <-time.After(backoffDelay(attempt)):
				}
				continue
			}
			return nil, &ConnectionError{
				Message:  err.Error(),
				Attempts: attempt + 1,
				Cause:    err,
			}
		}
		return resp, nil
	}
	return nil, &ConnectionError{
		Message:  lastErr.Error(),
		Attempts: c.maxRetries + 1,
		Cause:    lastErr,
	}
}

type apiError struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

func handleError(resp *http.Response) error {
	if resp.StatusCode < 400 {
		return nil
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	message := string(body)
	code := ""

	var ae apiError
	if json.Unmarshal(body, &ae) == nil && ae.Error.Message != "" {
		message = ae.Error.Message
		code = ae.Error.Code
	}

	e := &APIError{
		Message:    message,
		StatusCode: resp.StatusCode,
		Code:       code,
	}
	if resp.StatusCode == 404 {
		return &NotFoundError{APIError: *e}
	}
	return e
}

func (c *Client) jsonRequest(ctx context.Context, method, path string, body interface{}) (*http.Response, error) {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("cody: marshal request: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("cody: create request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	return c.doWithRetry(ctx, req)
}

func decodeJSON(resp *http.Response, v interface{}) error {
	defer resp.Body.Close()
	return json.NewDecoder(resp.Body).Decode(v)
}

// ── Health ──────────────────────────────────────────────────────────────────

// Health checks server health.
func (c *Client) Health(ctx context.Context) (*HealthResponse, error) {
	resp, err := c.jsonRequest(ctx, http.MethodGet, "/health", nil)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}
	var result HealthResponse
	if err := decodeJSON(resp, &result); err != nil {
		return nil, fmt.Errorf("cody: decode health: %w", err)
	}
	return &result, nil
}

// ── Run ─────────────────────────────────────────────────────────────────────

// Run executes an agent task and returns the result.
func (c *Client) Run(ctx context.Context, prompt string, opts ...RunOption) (*RunResult, error) {
	o := &runOptions{}
	for _, opt := range opts {
		opt(o)
	}

	body := map[string]interface{}{"prompt": prompt}
	if o.Workdir != "" {
		body["workdir"] = o.Workdir
	}
	if o.Model != "" {
		body["model"] = o.Model
	}
	if o.SessionID != nil {
		body["session_id"] = *o.SessionID
	}

	resp, err := c.jsonRequest(ctx, http.MethodPost, "/run", body)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}

	var result RunResult
	if err := decodeJSON(resp, &result); err != nil {
		return nil, fmt.Errorf("cody: decode run result: %w", err)
	}
	return &result, nil
}

// ── Stream ──────────────────────────────────────────────────────────────────

// Stream executes an agent task and returns a channel of streaming chunks.
// The channel is closed when the stream ends. Errors are delivered as chunks
// with Type == "error".
func (c *Client) Stream(ctx context.Context, prompt string, opts ...RunOption) (<-chan StreamChunk, error) {
	o := &runOptions{}
	for _, opt := range opts {
		opt(o)
	}

	body := map[string]interface{}{"prompt": prompt}
	if o.Workdir != "" {
		body["workdir"] = o.Workdir
	}
	if o.Model != "" {
		body["model"] = o.Model
	}
	if o.SessionID != nil {
		body["session_id"] = *o.SessionID
	}

	data, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("cody: marshal stream request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/run/stream", bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("cody: create stream request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	resp, err := c.doWithRetry(ctx, req)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		resp.Body.Close()
		return nil, err
	}

	ch := make(chan StreamChunk)
	go func() {
		defer close(ch)
		defer resp.Body.Close()

		scanner := bufio.NewScanner(resp.Body)
		for scanner.Scan() {
			line := scanner.Text()
			if !strings.HasPrefix(line, "data: ") {
				continue
			}
			var chunk StreamChunk
			if err := json.Unmarshal([]byte(line[6:]), &chunk); err != nil {
				continue
			}
			select {
			case ch <- chunk:
			case <-ctx.Done():
				return
			}
		}
	}()

	return ch, nil
}

// ── Tool ────────────────────────────────────────────────────────────────────

// Tool calls a tool directly, bypassing the agent.
func (c *Client) Tool(ctx context.Context, toolName string, params map[string]interface{}, opts ...RunOption) (*ToolResult, error) {
	o := &runOptions{}
	for _, opt := range opts {
		opt(o)
	}

	body := map[string]interface{}{
		"tool":   toolName,
		"params": params,
	}
	if o.Workdir != "" {
		body["workdir"] = o.Workdir
	}

	resp, err := c.jsonRequest(ctx, http.MethodPost, "/tool", body)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}

	var raw map[string]interface{}
	if err := decodeJSON(resp, &raw); err != nil {
		return nil, fmt.Errorf("cody: decode tool result: %w", err)
	}
	result, _ := raw["result"].(string)
	return &ToolResult{Result: result}, nil
}

// ── Sessions ────────────────────────────────────────────────────────────────

// CreateSession creates a new conversation session.
func (c *Client) CreateSession(ctx context.Context, opts ...CreateSessionOption) (*SessionInfo, error) {
	o := &createSessionOptions{Title: "New session"}
	for _, opt := range opts {
		opt(o)
	}

	params := url.Values{}
	params.Set("title", o.Title)
	params.Set("model", o.Model)
	params.Set("workdir", o.Workdir)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/sessions?"+params.Encode(), nil)
	if err != nil {
		return nil, fmt.Errorf("cody: create session request: %w", err)
	}

	resp, err := c.doWithRetry(ctx, req)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}

	var session SessionInfo
	if err := decodeJSON(resp, &session); err != nil {
		return nil, fmt.Errorf("cody: decode session: %w", err)
	}
	return &session, nil
}

// ListSessions returns recent sessions.
func (c *Client) ListSessions(ctx context.Context, limit int) ([]SessionInfo, error) {
	if limit <= 0 {
		limit = 20
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/sessions?limit="+strconv.Itoa(limit), nil)
	if err != nil {
		return nil, fmt.Errorf("cody: list sessions request: %w", err)
	}

	resp, err := c.doWithRetry(ctx, req)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}

	var raw struct {
		Sessions []SessionInfo `json:"sessions"`
	}
	if err := decodeJSON(resp, &raw); err != nil {
		return nil, fmt.Errorf("cody: decode sessions: %w", err)
	}
	return raw.Sessions, nil
}

// GetSession returns session detail with message history.
func (c *Client) GetSession(ctx context.Context, sessionID string) (*SessionDetail, error) {
	resp, err := c.jsonRequest(ctx, http.MethodGet, "/sessions/"+sessionID, nil)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}

	var detail SessionDetail
	if err := decodeJSON(resp, &detail); err != nil {
		return nil, fmt.Errorf("cody: decode session detail: %w", err)
	}
	return &detail, nil
}

// DeleteSession deletes a session.
func (c *Client) DeleteSession(ctx context.Context, sessionID string) error {
	resp, err := c.jsonRequest(ctx, http.MethodDelete, "/sessions/"+sessionID, nil)
	if err != nil {
		return err
	}
	if err := handleError(resp); err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// ── Skills ──────────────────────────────────────────────────────────────────

// ListSkills returns all available skills.
func (c *Client) ListSkills(ctx context.Context) ([]SkillInfo, error) {
	resp, err := c.jsonRequest(ctx, http.MethodGet, "/skills", nil)
	if err != nil {
		return nil, err
	}
	if err := handleError(resp); err != nil {
		return nil, err
	}

	var raw struct {
		Skills []SkillInfo `json:"skills"`
	}
	if err := decodeJSON(resp, &raw); err != nil {
		return nil, fmt.Errorf("cody: decode skills: %w", err)
	}
	return raw.Skills, nil
}
