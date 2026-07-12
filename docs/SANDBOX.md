# Sandbox

Cody has one process-execution boundary: `SandboxBackend` creates a
run-scoped `SandboxHandle`, and every child process is launched through that
handle. Backend selection is configuration, not application logic.

## Configuration

```json
{
  "sandbox": {
    "enabled": true,
    "backend": "auto",
    "image": "ubuntu:24.04",
    "fail_if_unavailable": true,
    "network_mode": "disabled",
    "allowed_domains": [],
    "denied_roots": ["~/.ssh", "~/.aws"],
    "cpu_count": 2,
    "memory_mb": 2048,
    "process_limit": 128,
    "timeout_seconds": 300,
    "env": {
      "GOCACHE": "/workspace/.cache/go-build",
      "GOPATH": "/workspace/.cache/gopath"
    }
  }
}
```

`auto` selects macOS Seatbelt on Darwin and bubblewrap on Linux. Production
services should normally choose `docker`, `podman`, or register a
`RemoteSandboxBackend`. Selection fails closed by default. Set
`fail_if_unavailable` to `false` only when explicitly accepting the
non-isolating `local-policy` fallback.

Network modes are `disabled`, `allowlist`, `proxied`, and `unrestricted`.
Seatbelt and container hostname allowlists require a policy proxy because those
kernels enforce sockets/IPs, not stable DNS names. Seatbelt requires a
`unix://` proxy; Docker/Podman additionally require `network_name` for an
administrator-created proxy-only network, preventing direct egress bypass.
HTTP MCP endpoints are also checked against the Run network policy.

## Remote providers

Implement `RemoteSandboxTransport` for the provider API, then register it:

```python
manager = SandboxManager()
manager.register(RemoteSandboxBackend(transport, name="remote"))
runtime = CodyRuntime(runner, sandbox_manager=manager)
```

The transport owns remote create/exec/spawn/pause/resume/snapshot/restore/fork
and terminate operations. Snapshot references must remain valid across service
restarts; Cody stores those references as Artifacts linked to Checkpoints.

## Trust boundary

Sandboxed guest capabilities include command tools, quality checks, stdio MCP,
LSP, and sub-agent command tools. Model API clients and Python extension code
(hooks, custom node handlers, provider adapters) run in the trusted host
process. Treat installed Python extensions as application code, not sandboxed
user code.
