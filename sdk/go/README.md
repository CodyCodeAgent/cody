# Cody Go SDK

Go client for the [Cody RPC Server](../../docs/API.md).

## Install

```bash
go get github.com/SUT-GC/cody-go
```

## Quick Start

```go
package main

import (
    "context"
    "fmt"
    "log"

    cody "github.com/SUT-GC/cody-go"
)

func main() {
    client := cody.NewClient("http://localhost:8000")
    ctx := context.Background()

    // Health check
    health, _ := client.Health(ctx)
    fmt.Println(health.Status, health.Version)

    // One-shot task
    result, err := client.Run(ctx, "create a hello world app")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println(result.Output)

    // With options
    result, _ = client.Run(ctx, "refactor auth.py",
        cody.WithWorkdir("/path/to/project"),
        cody.WithModel("anthropic:claude-sonnet-4-0"),
    )

    // Multi-turn session
    session, _ := client.CreateSession(ctx, cody.WithTitle("My task"))
    client.Run(ctx, "create Flask app", cody.WithSession(session.ID))
    client.Run(ctx, "add /health endpoint", cody.WithSession(session.ID))

    // Streaming
    ch, _ := client.Stream(ctx, "explain this code")
    for chunk := range ch {
        if chunk.Type == "text" {
            fmt.Print(chunk.Content)
        }
    }
    fmt.Println()

    // Direct tool call
    tool, _ := client.Tool(ctx, "read_file", map[string]interface{}{"path": "main.py"})
    fmt.Println(tool.Result)

    // List skills
    skills, _ := client.ListSkills(ctx)
    for _, s := range skills {
        fmt.Printf("  %s (%s)\n", s.Name, s.Source)
    }
}
```

## API

### Client

```go
// Create with defaults (timeout: 120s, retries: 3)
client := cody.NewClient("http://localhost:8000")

// Custom options
client := cody.NewClient("http://localhost:8000",
    cody.WithTimeout(30 * time.Second),
    cody.WithMaxRetries(5),
    cody.WithHTTPClient(customHTTPClient),
)
```

### Methods

| Method | Description |
|--------|-------------|
| `Health(ctx)` | Check server health |
| `Run(ctx, prompt, opts...)` | Execute agent task |
| `Stream(ctx, prompt, opts...)` | Stream agent response |
| `Tool(ctx, name, params, opts...)` | Call a tool directly |
| `CreateSession(ctx, opts...)` | Create a session |
| `ListSessions(ctx, limit)` | List recent sessions |
| `GetSession(ctx, id)` | Get session with messages |
| `DeleteSession(ctx, id)` | Delete a session |
| `ListSkills(ctx)` | List available skills |

### Run/Stream Options

```go
cody.WithWorkdir("/path")          // Set working directory
cody.WithModel("anthropic:...")    // Set model
cody.WithSession("session-id")    // Set session for multi-turn
```

### Error Handling

```go
result, err := client.Run(ctx, "task")
if err != nil {
    switch e := err.(type) {
    case *cody.NotFoundError:
        fmt.Println("Not found:", e.Message)
    case *cody.ConnectionError:
        fmt.Println("Connection failed after", e.Attempts, "attempts")
    case *cody.APIError:
        fmt.Println("API error:", e.Code, e.Message, e.StatusCode)
    }
}
```

### Streaming

```go
ch, err := client.Stream(ctx, "explain this code")
if err != nil {
    log.Fatal(err)
}

for chunk := range ch {
    switch chunk.Type {
    case "text":
        fmt.Print(chunk.Content)
    case "done":
        fmt.Println("\n--- Done ---")
    case "error":
        fmt.Println("Error:", chunk.Content)
    }
}
```

The channel is closed when the stream ends. Cancel the context to abort early.

## Features

- **Zero dependencies** — uses only Go standard library
- **Automatic retry** — exponential backoff on transient failures (default 3 retries)
- **Context support** — all methods accept `context.Context` for cancellation/timeout
- **Streaming** — channel-based SSE streaming with context cancellation
- **Type-safe errors** — `*Error`, `*NotFoundError`, `*ConnectionError`
- **Functional options** — clean, composable API configuration
