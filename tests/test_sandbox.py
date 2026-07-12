import platform
import shutil

import pytest

from cody.core.sandbox import (
    DockerSandboxBackend,
    FilesystemPolicy,
    LocalPolicySandboxBackend,
    NetworkMode,
    NetworkPolicy,
    RemoteSandboxBackend,
    ResourceLimits,
    SandboxBackend,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxManager,
    SandboxPolicyError,
    SandboxSpec,
    SandboxStatus,
    SandboxUnavailableError,
    bubblewrap_prefix,
    seatbelt_profile,
    sandbox_spec_from_config,
)
from cody.core.config import Config


def spec(tmp_path, **kwargs):
    return SandboxSpec(
        run_id="run_sandbox",
        workdir=tmp_path,
        backend=kwargs.pop("backend", "local-policy"),
        filesystem=FilesystemPolicy(
            read_roots=(tmp_path,), write_roots=(tmp_path,)
        ),
        metadata={"state_root": str(tmp_path / ".state")},
        **kwargs,
    )


@pytest.mark.asyncio
async def test_local_policy_exec_uses_argv_and_lifecycle(tmp_path):
    handle = await LocalPolicySandboxBackend().create(spec(tmp_path))

    result = await handle.exec(
        SandboxExecutionRequest(argv=("python3", "-c", "print('sandbox-ok')"))
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "sandbox-ok"
    assert result.argv[0] == "python3"
    await handle.pause()
    assert handle.status == SandboxStatus.PAUSED
    with pytest.raises(SandboxPolicyError):
        await handle.exec(SandboxExecutionRequest(argv=("true",)))
    await handle.resume()
    await handle.terminate()
    assert handle.status == SandboxStatus.TERMINATED


@pytest.mark.asyncio
async def test_local_policy_timeout_is_structured(tmp_path):
    handle = await LocalPolicySandboxBackend().create(
        spec(tmp_path, resources=ResourceLimits(timeout_seconds=0.01))
    )
    result = await handle.exec(
        SandboxExecutionRequest(argv=("python3", "-c", "import time; time.sleep(1)"))
    )
    assert result.timed_out is True
    assert result.returncode == 124


@pytest.mark.asyncio
async def test_host_secrets_are_not_inherited_implicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("CODY_TEST_SECRET", "must-not-leak")
    handle = await LocalPolicySandboxBackend().create(spec(tmp_path))
    result = await handle.exec(
        SandboxExecutionRequest(
            argv=("python3", "-c", "import os; print(os.getenv('CODY_TEST_SECRET', 'missing'))")
        )
    )
    assert result.stdout.strip() == "missing"


@pytest.mark.asyncio
@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="macOS Seatbelt is unavailable",
)
async def test_real_seatbelt_blocks_outside_write_and_network(tmp_path):
    from cody.core.sandbox import SeatbeltSandboxBackend

    handle = await SeatbeltSandboxBackend().create(
        spec(tmp_path, backend="seatbelt", network=NetworkPolicy(mode=NetworkMode.DISABLED))
    )
    outside = tmp_path.parent / "seatbelt-outside.txt"
    write = await handle.exec(
        SandboxExecutionRequest(
            argv=("/bin/sh", "-c", f"echo blocked > {outside}")
        )
    )
    network = await handle.exec(
        SandboxExecutionRequest(
            argv=("/usr/bin/curl", "--max-time", "2", "https://example.com")
        )
    )
    assert write.returncode != 0
    assert not outside.exists()
    assert network.returncode != 0

    nested_tmp = await handle.exec(
        SandboxExecutionRequest.shell(
            'mkdir -p "$TMPDIR/go-build-test" && test -d "$TMPDIR/go-build-test"'
        )
    )
    assert nested_tmp.returncode == 0, nested_tmp.stderr


@pytest.mark.asyncio
async def test_local_snapshot_restore_and_private_fork(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "value.txt").write_text("before")
    handle = await LocalPolicySandboxBackend().create(
        SandboxSpec(
            run_id="run_snapshot",
            workdir=workspace,
            backend="local-policy",
            filesystem=FilesystemPolicy(
                read_roots=(workspace,), write_roots=(workspace,), private_workspace=True
            ),
            metadata={"state_root": str(tmp_path / "state")},
        )
    )
    snapshot = await handle.snapshot()
    (workspace / "value.txt").write_text("after")
    await handle.restore(snapshot)
    assert (workspace / "value.txt").read_text() == "before"

    fork = await handle.fork(sandbox_id="sandbox_fork")
    assert fork.spec.workdir != workspace
    assert (fork.spec.workdir / "value.txt").read_text() == "before"


def test_seatbelt_profile_denies_by_default_and_scopes_network(tmp_path):
    profile = seatbelt_profile(
        spec(tmp_path, network=NetworkPolicy(mode=NetworkMode.DISABLED)).normalized()
    )
    assert "(deny default)" in profile
    assert "(allow file-read*)" in profile
    assert "(allow file-write*" in profile
    assert "(allow network*)" not in profile


def test_disabled_sandbox_preserves_legacy_network_compatibility(tmp_path):
    config = Config()
    config.sandbox.enabled = False
    generated = sandbox_spec_from_config(
        config, run_id="run_config", workdir=tmp_path
    )
    assert generated.backend == "local-policy"
    assert generated.network.mode == NetworkMode.UNRESTRICTED


def test_sandbox_config_explicit_environment_reaches_spec(tmp_path):
    config = Config()
    config.sandbox.enabled = True
    config.sandbox.backend = "seatbelt"
    config.sandbox.env = {"GOCACHE": str(tmp_path / ".cache")}
    generated = sandbox_spec_from_config(
        config, run_id="run_env", workdir=tmp_path
    )
    assert generated.env == {"GOCACHE": str(tmp_path / ".cache")}


def test_bubblewrap_prefix_is_read_only_and_network_isolated(tmp_path):
    prefix = bubblewrap_prefix(
        spec(tmp_path, network=NetworkPolicy(mode=NetworkMode.DISABLED)).normalized()
    )
    assert prefix[:2] == ("bwrap", "--die-with-parent")
    assert "--ro-bind" in prefix
    assert "--bind" in prefix
    assert "--unshare-net" in prefix


def test_docker_create_argv_enforces_resources_mounts_and_no_network(tmp_path):
    backend = DockerSandboxBackend()
    argv = backend.create_argv(
        spec(
            tmp_path,
            backend="docker",
            image="cody-test:latest",
            network=NetworkPolicy(mode=NetworkMode.DISABLED),
            resources=ResourceLimits(cpu_count=2, memory_mb=512, process_limit=64),
        ).normalized()
    )
    rendered = " ".join(argv)
    assert "--network none" in rendered
    assert "--cpus 2" in rendered
    assert "--memory 512m" in rendered
    assert "--pids-limit 64" in rendered
    assert f"{tmp_path}:{tmp_path}:rw" in rendered


class UnavailableBackend(SandboxBackend):
    name = "unavailable"
    async def available(self): return False
    async def create(self, spec): raise AssertionError("must not create")


@pytest.mark.asyncio
async def test_manager_fails_closed_or_explicitly_falls_back(tmp_path):
    manager = SandboxManager([LocalPolicySandboxBackend(), UnavailableBackend()])
    with pytest.raises(SandboxUnavailableError):
        await manager.create(spec(tmp_path, backend="unavailable"))
    fallback = await manager.create(
        spec(tmp_path, backend="unavailable", fail_if_unavailable=False)
    )
    assert fallback.backend_name == "local-policy"


class FakeRemote:
    def __init__(self):
        self.calls = []

    async def available(self):
        return True

    async def create(self, spec):
        self.calls.append("create")
        return "remote-1"

    async def exec(self, remote_id, request):
        self.calls.append("exec")
        return SandboxExecutionResult("remote", request.argv, "ok", "", 0, 0.1)

    async def pause(self, remote_id):
        self.calls.append("pause")

    async def resume(self, remote_id):
        self.calls.append("resume")

    async def snapshot(self, remote_id):
        self.calls.append("snapshot")
        return "snap-ref"

    async def restore(self, remote_id, reference):
        self.calls.append("restore")

    async def fork(self, remote_id, spec):
        self.calls.append("fork")
        return "remote-2"

    async def terminate(self, remote_id):
        self.calls.append("terminate")


@pytest.mark.asyncio
async def test_remote_backend_preserves_full_lifecycle(tmp_path):
    transport = FakeRemote()
    backend = RemoteSandboxBackend(transport)
    handle = await backend.create(spec(tmp_path, backend="remote"))
    result = await handle.exec(SandboxExecutionRequest(argv=("echo", "ok")))
    await handle.pause()
    await handle.resume()
    snapshot = await handle.snapshot()
    await handle.restore(snapshot)
    fork = await handle.fork()
    await handle.terminate()
    await fork.terminate()
    assert result.stdout == "ok"
    assert transport.calls == [
        "create", "exec", "pause", "resume", "snapshot", "restore",
        "fork", "terminate", "terminate",
    ]
