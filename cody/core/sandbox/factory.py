"""Translate Cody configuration into backend-neutral sandbox policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import (
    FilesystemPolicy,
    NetworkMode,
    NetworkPolicy,
    ResourceLimits,
    SandboxSpec,
)


def sandbox_spec_from_config(
    config: Any,
    *,
    run_id: str,
    workdir: str | Path,
    sandbox_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SandboxSpec:
    root = Path(workdir).expanduser().resolve()
    sandbox = config.sandbox
    allowed_roots = tuple(
        Path(item).expanduser().resolve() for item in config.security.allowed_roots
    )
    roots = (root, *allowed_roots)
    sandbox_metadata = dict(metadata or {})
    if sandbox.state_root:
        sandbox_metadata["state_root"] = sandbox.state_root
    sandbox_metadata["image_pull_policy"] = sandbox.image_pull_policy
    if sandbox.network_name:
        sandbox_metadata["network_name"] = sandbox.network_name
    kwargs: dict[str, Any] = {}
    if sandbox_id is not None:
        kwargs["sandbox_id"] = sandbox_id
    return SandboxSpec(
        run_id=run_id,
        workdir=root,
        backend=sandbox.backend if sandbox.enabled else "local-policy",
        image=sandbox.image,
        filesystem=FilesystemPolicy(
            read_roots=roots,
            write_roots=roots,
            denied_roots=tuple(
                Path(item).expanduser().resolve() for item in sandbox.denied_roots
            ),
            private_workspace=sandbox.private_workspace,
        ),
        network=NetworkPolicy(
            mode=(
                NetworkMode(sandbox.network_mode)
                if sandbox.enabled
                else NetworkMode.UNRESTRICTED
            ),
            allowed_domains=tuple(sandbox.allowed_domains),
            allowed_cidrs=tuple(sandbox.allowed_cidrs),
            proxy_url=sandbox.proxy_url,
        ),
        resources=ResourceLimits(
            cpu_count=sandbox.cpu_count,
            memory_mb=sandbox.memory_mb,
            process_limit=sandbox.process_limit,
            timeout_seconds=sandbox.timeout_seconds or config.security.command_timeout,
        ),
        env=dict(sandbox.env),
        metadata=sandbox_metadata,
        fail_if_unavailable=sandbox.fail_if_unavailable,
        **kwargs,
    )
