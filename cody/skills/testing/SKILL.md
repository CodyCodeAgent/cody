---
name: testing
description: Guidelines and patterns for writing effective tests across languages — pytest, Jest, Go testing, Rust cargo test, JUnit. Use when writing or improving tests.
metadata:
  author: cody
  version: "1.0"
---

# Testing Strategies

Guidelines and patterns for writing effective tests across languages and frameworks.

## General Principles

- **Test behavior, not implementation** — tests should verify what code does, not how it does it
- **One assertion per logical concept** — each test should verify one thing
- **Arrange-Act-Assert** — structure tests clearly: setup, execute, verify
- **Use descriptive names** — `test_returns_404_when_user_not_found` not `test_get_user`
- **Keep tests independent** — no test should depend on another test's state

## Test Types

### Unit Tests
Test individual functions/methods in isolation.
```bash
# Python
python3 -m pytest tests/unit/ -v

# JavaScript
npm test -- --testPathPattern="unit"

# Go
go test ./internal/... -v

# Rust
cargo test --lib
```

### Integration Tests
Test components working together (database, API, etc.).
```bash
# Python
python3 -m pytest tests/integration/ -v

# Go
go test ./tests/integration/... -v

# Rust
cargo test --test '*'
```

### End-to-End Tests
Test the full system from the user's perspective.
```bash
# Playwright (Python)
python3 -m pytest tests/e2e/ --headed

# Cypress (JavaScript)
npx cypress run

# API E2E
python3 -m pytest tests/e2e/ -v -k "api"
```

## Python Testing (pytest)

### Run tests
```bash
python3 -m pytest tests/ -v              # All tests, verbose
python3 -m pytest tests/test_auth.py -v  # Specific file
python3 -m pytest tests/ -k "login"      # Match by name
python3 -m pytest tests/ -x              # Stop on first failure
python3 -m pytest tests/ --tb=short      # Short tracebacks
python3 -m pytest tests/ --lf            # Rerun last failed
```

### Coverage
```bash
python3 -m pytest tests/ --cov=myproject --cov-report=term-missing
python3 -m pytest tests/ --cov=myproject --cov-report=html
```

### Fixtures
```python
import pytest

@pytest.fixture
def db():
    conn = create_connection()
    yield conn
    conn.close()

@pytest.fixture
def client(db):
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
```

### Parametrize
```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    assert uppercase(input) == expected
```

### Async tests
```python
import pytest

@pytest.mark.asyncio
async def test_async_fetch():
    result = await fetch_data("https://api.example.com")
    assert result.status == 200
```

### Mocking
```python
from unittest.mock import patch, MagicMock

def test_send_email():
    with patch("myapp.email.smtp_client") as mock_smtp:
        send_email("user@example.com", "Hello")
        mock_smtp.send.assert_called_once()
```

## JavaScript Testing (Jest / Vitest)

### Run tests
```bash
npm test                          # All tests
npm test -- --watch               # Watch mode
npm test -- --coverage            # Coverage
npm test -- --testPathPattern="auth"  # Specific tests
```

### Mocking
```javascript
jest.mock('./database');

test('fetches user', async () => {
  database.getUser.mockResolvedValue({ name: 'Alice' });
  const user = await getUser(1);
  expect(user.name).toBe('Alice');
});
```

## Go Testing

### Run tests
```bash
go test ./... -v                  # All tests, verbose
go test -run TestAuth ./...       # Match by name
go test -race ./...               # Race detector
go test -cover ./...              # Coverage
```

### Table-driven tests
```go
tests := []struct {
    name  string
    input string
    want  string
}{
    {"empty", "", ""},
    {"hello", "hello", "HELLO"},
}
for _, tt := range tests {
    t.Run(tt.name, func(t *testing.T) {
        got := ToUpper(tt.input)
        if got != tt.want {
            t.Errorf("ToUpper(%q) = %q, want %q", tt.input, got, tt.want)
        }
    })
}
```

## Rust Testing

### Run tests
```bash
cargo test                        # All tests
cargo test test_name              # Specific test
cargo test -- --nocapture         # Show output
cargo test --doc                  # Doc tests
```

## When to Write Tests

- **Always**: Public API functions, business logic, data transformations
- **Usually**: Error handling paths, edge cases, bug fixes (regression tests)
- **Sometimes**: Internal helpers (test via public API instead), UI layout
- **Rarely**: Simple getters/setters, generated code, third-party wrappers

## Notes

- Write the test BEFORE fixing a bug (red-green-refactor)
- Mock external services, not internal logic
- Use factories/builders for test data, not raw constructors
- Keep test files next to source (Go) or in a parallel `tests/` directory (Python)
- Run tests in CI with `-x` (fail fast) for quicker feedback
- Use `--lf` (pytest) or `--onlyFailures` (Jest) to iterate on failures
