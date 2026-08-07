#!/usr/bin/env python3
"""Run opt-in integration checks against Cody production backends.

External credentials are read only from environment variables. The JSON report
contains service versions and capability results, never connection strings or
credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from uuid import uuid4

from cody.core.sandbox import (
    BubblewrapSandboxBackend,
    DockerSandboxBackend,
    FilesystemPolicy,
    NetworkMode,
    NetworkPolicy,
    RemoteSandboxBackend,
    ResourceLimits,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxProcess,
    SandboxSpec,
)


def _emit(results: list[dict[str, Any]]) -> int:
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 1 if any(item["status"] == "FAIL" for item in results) else 0


def _pass(name: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "PASS", "details": details}


def _skip(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "SKIP", "details": {"reason": reason}}


def _fail(name: str, exc: BaseException) -> dict[str, Any]:
    return {
        "name": name,
        "status": "FAIL",
        "details": {"error_type": type(exc).__name__, "error": str(exc)},
    }


def _pg_child(role: str) -> int:
    from cody.core.runtime import (
        ApprovalRequestRecord,
        ArtifactRecord,
        ArtifactType,
        CheckpointRecord,
        RunEvent,
        RunEventType,
        RunRecord,
        RunStatus,
        RuntimeAuditRecord,
        RuntimeStoreBundle,
        StepRecord,
        StepType,
    )

    dsn = os.environ["CODY_VERIFY_POSTGRES_DSN"]
    schema = os.environ["CODY_VERIFY_POSTGRES_SCHEMA"]
    run_id = os.environ["CODY_VERIFY_RUN_ID"]
    approval_id = os.environ["CODY_VERIFY_APPROVAL_ID"]
    bundle = RuntimeStoreBundle.postgres(dsn, schema=schema)
    if role == "writer":
        run = RunRecord(task="production backend validation", run_id=run_id).transition(
            RunStatus.WAITING
        )
        step = StepRecord(
            run_id=run_id, step_id="step_pg", step_type=StepType.APPROVAL
        ).wait()
        bundle.run_store.save_run(run)
        bundle.run_store.save_step(step)
        bundle.trace_store.append(RunEvent(RunEventType.RUN_WAITING, run_id=run_id))
        bundle.checkpoint_store.save(
            CheckpointRecord(
                checkpoint_id="checkpoint_pg",
                run_id=run_id,
                step_id=step.step_id,
                workflow_state={"next": "approval"},
                pending_approval_ids=[approval_id],
            )
        )
        bundle.artifact_store.save(
            ArtifactRecord(
                artifact_id="artifact_pg",
                run_id=run_id,
                artifact_type=ArtifactType.TEST_REPORT,
                content={"backend": "postgres"},
            )
        )
        bundle.approval_store.save(
            ApprovalRequestRecord(
                approval_id=approval_id,
                run_id=run_id,
                node_id="approval",
                request={"question": "continue?"},
            )
        )
        bundle.audit_store.append(
            RuntimeAuditRecord(
                action="validation.write", actor_id="process-writer", ok=True, run_id=run_id
            )
        )
        bundle.control_store.request_pause(run_id, before_node_id="approval")
        return 0

    run = bundle.run_store.get_run(run_id)
    assert run is not None and run.status == RunStatus.WAITING
    assert bundle.run_store.get_step("step_pg") is not None
    assert len(bundle.trace_store.list_events(run_id)) == 1
    assert bundle.checkpoint_store.latest(run_id) is not None
    assert bundle.artifact_store.get("artifact_pg") is not None
    assert bundle.approval_store.get(approval_id) is not None
    assert bundle.audit_store.list(actor_id="process-writer")
    assert bundle.control_store.should_pause(run_id, "approval")
    bundle.approval_store.approve(approval_id, {"approved": True, "by": "process-reader"})
    bundle.control_store.clear_pause(run_id)
    bundle.control_store.request_cancel(run_id, before_node_id="finalize")
    return 0


def verify_postgres() -> dict[str, Any]:
    from cody.core.runtime import RuntimeStoreBundle

    name = "postgres-multiprocess"
    dsn = os.environ.get("CODY_VERIFY_POSTGRES_DSN")
    if not dsn:
        return _skip(name, "CODY_VERIFY_POSTGRES_DSN is not set")
    schema = f"cody_verify_{uuid4().hex[:12]}"
    run_id = f"run_{uuid4().hex}"
    approval_id = f"approval_{uuid4().hex}"
    env = {
        **os.environ,
        "CODY_VERIFY_POSTGRES_SCHEMA": schema,
        "CODY_VERIFY_RUN_ID": run_id,
        "CODY_VERIFY_APPROVAL_ID": approval_id,
    }
    try:
        import psycopg

        bundle = RuntimeStoreBundle.postgres(dsn, schema=schema)
        for role in ("writer", "reader"):
            subprocess.run(
                [sys.executable, __file__, "--_pg-child", role],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        approved = bundle.approval_store.get(approval_id)
        assert approved is not None and approved.status.value == "approved"
        assert not bundle.control_store.should_pause(run_id, "approval")
        assert bundle.control_store.should_cancel(run_id, "finalize")
        with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            version = cursor.fetchone()[0]
            cursor.execute(
                "SELECT kind, count(*) FROM "
                f'"{schema}"."cody_runtime_records" GROUP BY kind ORDER BY kind'
            )
            kinds = {kind: count for kind, count in cursor.fetchall()}
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = %s ORDER BY indexname",
                (schema,),
            )
            indexes = [row[0] for row in cursor.fetchall()]
        expected = {"approval", "artifact", "audit", "checkpoint", "control", "event", "run", "step"}
        assert expected.issubset(kinds)
        assert len(indexes) >= 3
        return _pass(
            name,
            server=f"PostgreSQL {version}",
            independent_processes=2,
            record_kinds=sorted(kinds),
            indexes=indexes,
        )
    except BaseException as exc:
        return _fail(name, exc)
    finally:
        try:
            import psycopg

            with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except BaseException:
            pass


def verify_s3() -> dict[str, Any]:
    from cody.core.runtime import ArtifactRecord, ArtifactType, InMemoryArtifactStore
    from cody.core.runtime.object_storage import ObjectArtifactStore, S3ObjectStorage

    name = "s3-minio-artifacts"
    endpoint = os.environ.get("CODY_VERIFY_S3_ENDPOINT")
    bucket = os.environ.get("CODY_VERIFY_S3_BUCKET")
    access_key = os.environ.get("CODY_VERIFY_S3_ACCESS_KEY")
    secret_key = os.environ.get("CODY_VERIFY_S3_SECRET_KEY")
    if not all((endpoint, bucket, access_key, secret_key)):
        return _skip(name, "S3 endpoint, bucket, access key, and secret key are required")
    prefix = f"tenants/validation-{uuid4().hex[:12]}"
    try:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )
        try:
            client.create_bucket(Bucket=bucket)
        except client.exceptions.BucketAlreadyOwnedByYou:
            pass
        objects = S3ObjectStorage(
            bucket,
            prefix=prefix,
            client=client,
            put_options={"ServerSideEncryption": "AES256"},
        )
        catalog = InMemoryArtifactStore()
        store = ObjectArtifactStore(catalog, objects)
        artifact = ArtifactRecord(
            run_id="run_s3",
            artifact_id="artifact_s3",
            artifact_type=ArtifactType.TEST_REPORT,
            content={"result": "S3_OK", "payload": "external"},
        )
        store.save(artifact)
        hydrated = store.get(artifact.artifact_id)
        listed = store.list(run_id=artifact.run_id)
        catalog_record = catalog.get(artifact.artifact_id)
        assert hydrated is not None and hydrated.content == artifact.content
        assert len(listed) == 1 and listed[0].content == artifact.content
        assert catalog_record is not None
        assert catalog_record.content == {
            "object_key": "runs/run_s3/artifacts/artifact_s3.json"
        }
        object_key = f"{prefix}/runs/run_s3/artifacts/artifact_s3.json"
        head = client.head_object(Bucket=bucket, Key=object_key)
        assert head.get("ServerSideEncryption") == "AES256"
        assert client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("KeyCount") == 1
        objects.delete("runs/run_s3/artifacts/artifact_s3.json")
        assert client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("KeyCount") == 0
        server = client.meta.endpoint_url
        return _pass(
            name,
            service="S3-compatible object storage",
            endpoint_scheme=str(server).split(":", 1)[0],
            tenant_prefix=True,
            server_side_encryption="AES256",
            catalog_payload_externalized=True,
            delete_verified=True,
        )
    except BaseException as exc:
        return _fail(name, exc)


class _RemoteTransport:
    def __init__(self) -> None:
        self.instances: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}

    async def available(self) -> bool:
        return True

    async def create(self, spec: SandboxSpec) -> str:
        remote_id = f"remote-{uuid4().hex}"
        self.instances[remote_id] = {"spec": spec, "value": "created", "paused": False}
        return remote_id

    async def exec(self, remote_id: str, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        instance = self.instances[remote_id]
        instance["value"] = "executed"
        return SandboxExecutionResult(remote_id, request.argv, "REMOTE_OK", "", 0, 0.01)

    async def spawn(
        self, remote_id: str, request: SandboxExecutionRequest
    ) -> SandboxProcess:
        self.instances[remote_id]["spawned"] = list(request.argv)
        return _CompletedRemoteProcess()

    async def pause(self, remote_id: str) -> None:
        self.instances[remote_id]["paused"] = True

    async def resume(self, remote_id: str) -> None:
        self.instances[remote_id]["paused"] = False

    async def snapshot(self, remote_id: str) -> str:
        reference = f"provider://snapshots/{uuid4().hex}"
        self.snapshots[reference] = dict(self.instances[remote_id])
        return reference

    async def restore(self, remote_id: str, reference: str) -> None:
        self.instances[remote_id] = dict(self.snapshots[reference])

    async def fork(self, remote_id: str, spec: SandboxSpec) -> str:
        fork_id = f"remote-{uuid4().hex}"
        self.instances[fork_id] = {**self.instances[remote_id], "spec": spec}
        return fork_id

    async def terminate(self, remote_id: str) -> None:
        self.instances.pop(remote_id, None)


class _CompletedRemoteProcess(SandboxProcess):
    stdin = None
    stdout = None
    stderr = None

    @property
    def returncode(self) -> int:
        return 0

    async def wait(self) -> int:
        return 0

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        return b"REMOTE_PROCESS_OK", b""

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None


async def _verify_remote_async() -> dict[str, Any]:
    name = "remote-sandbox-contract"
    transport = _RemoteTransport()
    try:
        with tempfile.TemporaryDirectory(prefix="cody-remote-") as raw:
            workdir = Path(raw)
            spec = _sandbox_spec(workdir, "remote")
            first = await RemoteSandboxBackend(transport).create(spec)
            result = await first.exec(SandboxExecutionRequest(argv=("verify",)))
            process = await first.spawn(SandboxExecutionRequest(argv=("background",)))
            stdout, stderr = await process.communicate()
            await first.pause()
            await first.resume()
            snapshot = await first.snapshot()
            fork = await first.fork()
            # Simulate a new client process attaching through a durable provider
            # reference: create a fresh handle, then restore the old snapshot.
            recovered = await RemoteSandboxBackend(transport).create(spec)
            await recovered.restore(snapshot)
            assert snapshot.reference.startswith("provider://snapshots/")
            assert result.stdout == "REMOTE_OK"
            assert stdout == b"REMOTE_PROCESS_OK" and not stderr
            assert transport.instances[recovered.remote_id]["value"] == "executed"
            await first.terminate()
            await fork.terminate()
            await recovered.terminate()
        return _pass(
            name,
            provider="in-process contract transport",
            lifecycle=["create", "exec", "spawn", "pause", "resume", "snapshot", "restore", "fork", "terminate"],
            durable_reference_contract=True,
            hosted_provider=False,
        )
    except BaseException as exc:
        return _fail(name, exc)


def _sandbox_spec(workdir: Path, backend: str) -> SandboxSpec:
    return SandboxSpec(
        run_id=f"run_{backend}",
        sandbox_id=f"verify_{backend}_{uuid4().hex[:8]}",
        workdir=workdir,
        backend=backend,
        image="alpine:3.20",
        filesystem=FilesystemPolicy(read_roots=(workdir,), write_roots=(workdir,)),
        network=NetworkPolicy(mode=NetworkMode.DISABLED),
        resources=ResourceLimits(
            cpu_count=0.5,
            memory_mb=128,
            process_limit=32,
            timeout_seconds=3,
        ),
    )


async def _verify_container_async(executable: str) -> dict[str, Any]:
    name = f"{executable}-sandbox"
    if shutil.which(executable) is None:
        return _skip(name, f"{executable} executable is unavailable")
    backend = DockerSandboxBackend(executable)
    if not await backend.available():
        return _skip(name, f"{executable} daemon is unavailable")
    handle = None
    snapshot_reference: str | None = None
    try:
        # Desktop VM runtimes share the user home but not macOS' /private/tmp.
        # A home-based temporary directory therefore verifies the actual bind
        # mount instead of accidentally writing to a VM-local lookalike path.
        with tempfile.TemporaryDirectory(
            prefix=f".cody-{executable}-", dir=Path.home()
        ) as raw:
            workdir = Path(raw).resolve()
            handle = await backend.create(_sandbox_spec(workdir, executable))
            write = await handle.exec(
                SandboxExecutionRequest.shell("printf CONTAINER_OK > verified.txt && cat verified.txt")
            )
            readonly = await handle.exec(
                SandboxExecutionRequest.shell("touch /usr/cody-must-not-write"),
            )
            network = await handle.exec(
                SandboxExecutionRequest.shell("test \"$(wc -l < /proc/net/route)\" -eq 1")
            )
            timeout = await handle.exec(
                SandboxExecutionRequest.shell("sleep 5", timeout_seconds=0.25)
            )
            await handle.pause()
            await handle.resume()
            snapshot = await handle.snapshot()
            snapshot_reference = snapshot.reference
            assert write.stdout == "CONTAINER_OK"
            assert (workdir / "verified.txt").read_text() == "CONTAINER_OK"
            assert readonly.returncode != 0
            assert network.returncode == 0
            assert timeout.timed_out
            container_id = handle.container_id
            await handle.terminate()
            handle = None
            absent = subprocess.run(
                [executable, "inspect", container_id], capture_output=True, timeout=15
            )
            assert absent.returncode != 0
            inspect = subprocess.run(
                [executable, "image", "inspect", snapshot.reference],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert json.loads(inspect.stdout)
        return _pass(
            name,
            executable=executable,
            workspace_mount="read-write",
            root_filesystem="read-only",
            network="none",
            resources={"cpu": 0.5, "memory_mb": 128, "pids": 32},
            timeout=True,
            process_tree_cleanup=True,
            snapshot=True,
        )
    except BaseException as exc:
        return _fail(name, exc)
    finally:
        if handle is not None:
            try:
                await handle.terminate()
            except BaseException:
                pass
        if snapshot_reference:
            subprocess.run(
                [executable, "image", "rm", "-f", snapshot_reference],
                capture_output=True,
                timeout=30,
            )


async def _verify_bubblewrap_async() -> dict[str, Any]:
    name = "bubblewrap-sandbox"
    if platform.system() != "Linux" or shutil.which("bwrap") is None:
        return _skip(name, "requires Linux and the bwrap executable")
    handle = None
    try:
        with tempfile.TemporaryDirectory(prefix="cody-bwrap-") as raw:
            workdir = Path(raw).resolve()
            handle = await BubblewrapSandboxBackend().create(_sandbox_spec(workdir, "bubblewrap"))
            write = await handle.exec(
                SandboxExecutionRequest.shell("printf BWRAP_OK > verified.txt && cat verified.txt")
            )
            readonly = await handle.exec(
                SandboxExecutionRequest.shell("touch /usr/cody-must-not-write")
            )
            network = await handle.exec(
                SandboxExecutionRequest.shell(
                    "test \"$(wc -l < /proc/net/route)\" -eq 1"
                )
            )
            timeout = await handle.exec(
                SandboxExecutionRequest.shell("sleep 5", timeout_seconds=0.25)
            )
            assert write.stdout == "BWRAP_OK", f"workspace write failed: {write}"
            assert readonly.returncode != 0, "bubblewrap root filesystem was writable"
            assert network.returncode == 0, f"network namespace check failed: {network}"
            assert timeout.timed_out, f"timeout was not enforced: {timeout}"
            await handle.terminate()
            handle = None
        return _pass(
            name,
            mount_namespace=True,
            workspace_write=True,
            root_read_only=True,
            network_namespace=True,
            timeout=True,
            effective_uid=os.geteuid(),
        )
    except BaseException as exc:
        return _fail(name, exc)
    finally:
        if handle is not None:
            try:
                await handle.terminate()
            except BaseException:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "backends",
        nargs="*",
        choices=("postgres", "s3", "docker", "podman", "bubblewrap", "remote"),
        default=None,
    )
    parser.add_argument("--_pg-child", choices=("writer", "reader"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._pg_child:
        return _pg_child(args._pg_child)
    selected = list(
        args.backends
        or ("postgres", "s3", "docker", "podman", "bubblewrap", "remote")
    )
    results: list[dict[str, Any]] = []
    if "postgres" in selected:
        results.append(verify_postgres())
    if "s3" in selected:
        results.append(verify_s3())
    if "docker" in selected:
        results.append(asyncio.run(_verify_container_async("docker")))
    if "podman" in selected:
        results.append(asyncio.run(_verify_container_async("podman")))
    if "bubblewrap" in selected:
        results.append(asyncio.run(_verify_bubblewrap_async()))
    if "remote" in selected:
        results.append(asyncio.run(_verify_remote_async()))
    return _emit(results)


if __name__ == "__main__":
    raise SystemExit(main())
