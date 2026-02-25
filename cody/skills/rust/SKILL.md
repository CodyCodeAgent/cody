# Rust Project Management

Manage Rust projects, dependencies, and tooling using Cargo.

## Prerequisites

- Rust toolchain must be installed: `rustc --version`
- Cargo must be available: `cargo --version`
- Install via: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

## Project Setup

### Create a new project
```bash
cargo new my-project          # Binary project
cargo new my-lib --lib        # Library project
cargo init                    # Initialize in current directory
```

### Project structure
```
my-project/
├── Cargo.toml
├── src/
│   ├── main.rs              # Binary entry point
│   └── lib.rs               # Library entry point
├── tests/                   # Integration tests
├── benches/                 # Benchmarks
└── examples/                # Example programs
```

## Dependency Management

### Add dependencies (Cargo.toml)
```toml
[dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
anyhow = "1.0"
clap = { version = "4", features = ["derive"] }

[dev-dependencies]
pretty_assertions = "1"
```

### Using cargo-add
```bash
cargo add serde --features derive
cargo add tokio --features full
cargo add pretty_assertions --dev
cargo remove unused-crate
```

## Build & Run

```bash
cargo build                  # Debug build
cargo build --release        # Release build (optimized)
cargo run                    # Build and run
cargo run --release          # Run release build
cargo run -- arg1 arg2       # Pass arguments
cargo run --example my_example  # Run an example
```

## Testing

```bash
cargo test                   # Run all tests
cargo test test_name         # Run specific test
cargo test -- --nocapture    # Show println! output
cargo test --lib             # Only unit tests
cargo test --test integration_test  # Specific integration test
cargo test --doc             # Documentation tests
```

### Test patterns
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_something() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    #[should_panic(expected = "overflow")]
    fn test_panic() {
        overflow_function();
    }

    #[tokio::test]
    async fn test_async() {
        let result = async_function().await;
        assert!(result.is_ok());
    }
}
```

## Linting & Formatting

```bash
cargo fmt                    # Format code
cargo fmt -- --check         # Check formatting (CI)
cargo clippy                 # Lint
cargo clippy -- -D warnings  # Treat warnings as errors (CI)
```

### Clippy configuration (clippy.toml or Cargo.toml)
```toml
[lints.clippy]
pedantic = "warn"
nursery = "warn"
```

## Documentation

```bash
cargo doc                    # Generate docs
cargo doc --open             # Generate and open in browser
cargo doc --no-deps          # Skip dependency docs
```

## Common Patterns

### Error handling with anyhow/thiserror
```bash
cargo add anyhow             # Application error handling
cargo add thiserror          # Library error types
```

### Async runtime (Tokio)
```bash
cargo add tokio --features full
```

### Web server (Axum)
```bash
cargo add axum tokio --features tokio/full
cargo add tower-http --features cors,trace
```

### CLI application (Clap)
```bash
cargo add clap --features derive
```

### Serialization (Serde)
```bash
cargo add serde --features derive
cargo add serde_json
```

## Workspace (Monorepo)

```toml
# Root Cargo.toml
[workspace]
members = ["crates/*"]

[workspace.dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
```

```bash
cargo build -p my-crate      # Build specific crate
cargo test -p my-crate       # Test specific crate
```

## Cross-Compilation

```bash
rustup target add x86_64-unknown-linux-musl
cargo build --target x86_64-unknown-linux-musl --release
```

## Notes

- Use `cargo clippy` before committing — it catches common mistakes
- Prefer `thiserror` for library error types, `anyhow` for applications
- Use `#[derive(Debug, Clone)]` liberally
- Add `Cargo.lock` to git for binaries, exclude for libraries
- Use `cargo update` to update dependencies within semver ranges
- Profile with `cargo flamegraph` (install: `cargo install flamegraph`)
