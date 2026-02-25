---
name: go
description: Manage Go projects, modules, dependencies, testing, benchmarks, and cross-compilation. Use when working with Go code.
metadata:
  author: cody
  version: "1.0"
compatibility: Requires go 1.21+
---

# Go Project Management

Manage Go projects, modules, dependencies, and tooling.

## Prerequisites

- Go must be installed: `go version`
- Minimum recommended: Go 1.21+

## Project Setup

### Initialize a module
```bash
go mod init github.com/user/myproject
```

### Project structure
```
myproject/
├── go.mod
├── go.sum
├── main.go                  # Entry point (cmd)
├── cmd/
│   └── server/main.go       # Multiple entry points
├── internal/                # Private packages
│   ├── handler/
│   └── service/
├── pkg/                     # Public packages
└── _test.go files           # Tests (alongside source)
```

## Dependency Management

```bash
go get github.com/gin-gonic/gin          # Add dependency
go get github.com/gin-gonic/gin@v1.9.1   # Specific version
go get -u ./...                           # Update all dependencies
go mod tidy                               # Remove unused, add missing
go mod download                           # Download dependencies
go mod vendor                             # Vendor dependencies
```

## Build & Run

```bash
go run .                     # Run current package
go run ./cmd/server          # Run specific entry point
go build -o bin/server .     # Build binary
go build -o bin/server -ldflags="-s -w" .  # Smaller binary
go install ./...             # Install to $GOPATH/bin
```

## Testing

```bash
go test ./...                # Test all packages
go test -v ./...             # Verbose output
go test -run TestFoo ./...   # Run specific test
go test -count=1 ./...       # Disable test caching
go test -race ./...          # Enable race detector
go test -cover ./...         # Coverage summary
go test -coverprofile=coverage.out ./...   # Coverage file
go tool cover -html=coverage.out           # View coverage in browser
```

### Test patterns
```go
func TestAdd(t *testing.T) {
    got := Add(2, 3)
    want := 5
    if got != want {
        t.Errorf("Add(2, 3) = %d, want %d", got, want)
    }
}

// Table-driven tests
func TestAdd(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {"positive", 2, 3, 5},
        {"zero", 0, 0, 0},
        {"negative", -1, 1, 0},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            if got := Add(tt.a, tt.b); got != tt.want {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
            }
        })
    }
}
```

### Benchmarks
```bash
go test -bench=. -benchmem ./...
```

## Linting & Formatting

```bash
gofmt -w .                   # Format code
go vet ./...                 # Static analysis
```

### golangci-lint (recommended)
```bash
# Install
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest

# Run
golangci-lint run ./...
```

### Configuration (.golangci.yml)
```yaml
linters:
  enable:
    - errcheck
    - govet
    - staticcheck
    - unused
    - gosimple
    - ineffassign
```

## Common Patterns

### HTTP server (standard library)
```go
http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
    w.Write([]byte("ok"))
})
http.ListenAndServe(":8080", nil)
```

### HTTP server (Gin)
```bash
go get github.com/gin-gonic/gin
```

### HTTP server (Chi)
```bash
go get github.com/go-chi/chi/v5
```

### gRPC
```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
```

### Database (sqlx)
```bash
go get github.com/jmoiron/sqlx
go get github.com/lib/pq           # PostgreSQL
go get github.com/mattn/go-sqlite3  # SQLite
```

### CLI (Cobra)
```bash
go get github.com/spf13/cobra
go install github.com/spf13/cobra-cli@latest
cobra-cli init
cobra-cli add serve
```

## Cross-Compilation

```bash
GOOS=linux GOARCH=amd64 go build -o bin/server-linux .
GOOS=darwin GOARCH=arm64 go build -o bin/server-mac .
GOOS=windows GOARCH=amd64 go build -o bin/server.exe .
```

## Notes

- Use `go mod tidy` after adding/removing imports
- Tests go in `*_test.go` files alongside source
- Use `internal/` to prevent external packages from importing
- Always handle errors — don't use `_` for error returns
- Use `go vet` and `golangci-lint` before committing
- Race detector (`-race`) is essential for concurrent code
- Add `go.sum` to version control
