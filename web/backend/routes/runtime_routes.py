"""Canonical Runtime HTTP API backed by shared durable stores."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from cody.core.runtime import CodyRuntime, RuntimeAPIResponse

from ..state import (
    get_active_runtime_run,
    get_config,
    get_runtime_bundle,
    register_runtime_run,
)

router = APIRouter(prefix="/runtime", tags=["runtime"])
logger = logging.getLogger(__name__)


class RuntimeStartRequest(BaseModel):
    prompt: str = Field(min_length=1)
    workdir: str | None = None
    run_id: str | None = None
    max_steps: int = Field(default=100, ge=1)


class RuntimeControlRequest(BaseModel):
    workdir: str | None = None
    checkpoint_id: str | None = None
    max_steps: int = Field(default=100, ge=1)


class RuntimeForkRequest(BaseModel):
    checkpoint_id: str
    workdir: str | None = None
    new_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=100, ge=1)


class ApprovalDecisionRequest(BaseModel):
    workdir: str | None = None
    response: dict[str, Any] = Field(default_factory=dict)


def _workdir(value: str | None) -> Path:
    path = Path(value).expanduser().resolve() if value else Path.cwd().resolve()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Invalid workdir: {path}")
    return path


def _interface(workdir: str | None):
    return get_runtime_bundle(_workdir(workdir)).interface()


def _response(response: RuntimeAPIResponse) -> dict[str, Any]:
    if not response.ok:
        code = 404 if response.error and "not found" in response.error.lower() else 400
        raise HTTPException(status_code=code, detail=response.error)
    return response.data


async def _finish_runtime(runtime: CodyRuntime, handle) -> None:
    try:
        await handle.result()
    except Exception:
        logger.info("Runtime run %s ended without success", handle.run_id, exc_info=True)
    finally:
        await runtime.close()


def _register(runtime: CodyRuntime, handle) -> None:
    task = asyncio.create_task(
        _finish_runtime(runtime, handle),
        name=f"web-runtime-{handle.run_id}",
    )
    register_runtime_run(handle.run_id, runtime, handle, task)


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_runtime_run(request: RuntimeStartRequest):
    workdir = _workdir(request.workdir)
    stores = get_runtime_bundle(workdir)
    runtime = CodyRuntime.from_config(get_config(workdir), workdir, stores=stores)
    handle = await runtime.start(
        request.prompt,
        run_id=request.run_id,
        max_steps=request.max_steps,
    )
    _register(runtime, handle)
    return {"run_id": handle.run_id, "status": handle.record.status.value}


@router.get("/runs")
async def list_runtime_runs(
    workdir: str | None = None,
    run_status: str | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
):
    return _response(
        _interface(workdir).list_runs(
            status=run_status,
            offset=offset,
            limit=limit,
        )
    )


@router.get("/runs/{run_id}")
async def get_runtime_run(run_id: str, workdir: str | None = None):
    interface = _interface(workdir)
    run = _response(interface.get_run(run_id))
    steps = _response(interface.list_steps(run_id))
    return {**run, **steps}


@router.get("/runs/{run_id}/timeline")
async def get_runtime_timeline(run_id: str, workdir: str | None = None):
    return _response(_interface(workdir).get_timeline(run_id))


@router.get("/runs/{run_id}/metrics")
async def get_runtime_metrics(run_id: str, workdir: str | None = None):
    return _response(_interface(workdir).get_metrics(run_id))


@router.get("/runs/{run_id}/checkpoints")
async def list_runtime_checkpoints(run_id: str, workdir: str | None = None):
    return _response(_interface(workdir).list_checkpoints(run_id))


@router.get("/runs/{run_id}/artifacts")
async def list_runtime_artifacts(run_id: str, workdir: str | None = None):
    return _response(_interface(workdir).list_artifacts(run_id=run_id))


@router.post("/runs/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_runtime_run(run_id: str, request: RuntimeControlRequest):
    workdir = _workdir(request.workdir)
    stores = get_runtime_bundle(workdir)
    runtime = CodyRuntime.from_config(get_config(workdir), workdir, stores=stores)
    try:
        handle = await runtime.resume(run_id, max_steps=request.max_steps)
    except Exception as exc:
        await runtime.close()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _register(runtime, handle)
    return {"run_id": handle.run_id, "status": "resuming"}


@router.post("/runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_runtime_run(run_id: str, request: RuntimeControlRequest):
    workdir = _workdir(request.workdir)
    stores = get_runtime_bundle(workdir)
    runtime = CodyRuntime.from_config(get_config(workdir), workdir, stores=stores)
    try:
        handle = await runtime.retry(
            run_id,
            checkpoint_id=request.checkpoint_id,
            max_steps=request.max_steps,
        )
    except Exception as exc:
        await runtime.close()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _register(runtime, handle)
    return {"run_id": handle.run_id, "status": "retrying"}


@router.post("/runs/{run_id}/recover", status_code=status.HTTP_202_ACCEPTED)
async def recover_runtime_run(run_id: str, request: RuntimeControlRequest):
    workdir = _workdir(request.workdir)
    stores = get_runtime_bundle(workdir)
    runtime = CodyRuntime.from_config(get_config(workdir), workdir, stores=stores)
    try:
        handle = await runtime.recover(run_id, max_steps=request.max_steps)
    except Exception as exc:
        await runtime.close()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _register(runtime, handle)
    return {"run_id": handle.run_id, "status": "recovering"}


@router.post("/forks", status_code=status.HTTP_202_ACCEPTED)
async def fork_runtime_run(request: RuntimeForkRequest):
    workdir = _workdir(request.workdir)
    stores = get_runtime_bundle(workdir)
    runtime = CodyRuntime.from_config(get_config(workdir), workdir, stores=stores)
    try:
        handle = await runtime.fork(
            request.checkpoint_id,
            new_run_id=request.new_run_id,
            metadata=request.metadata,
            max_steps=request.max_steps,
        )
    except Exception as exc:
        await runtime.close()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _register(runtime, handle)
    return {"run_id": handle.run_id, "status": "forked"}


@router.post("/runs/{run_id}/cancel")
async def cancel_runtime_run(run_id: str, workdir: str | None = None):
    control = _response(_interface(workdir).request_cancel(run_id))
    active = get_active_runtime_run(run_id)
    if active is not None:
        _, handle, _ = active
        handle.cancel()
    return {**control, "status": "cancelling"}


@router.post("/runs/{run_id}/pause")
async def pause_runtime_run(run_id: str, workdir: str | None = None):
    return _response(_interface(workdir).request_pause(run_id))


@router.get("/approvals")
async def list_runtime_approvals(
    workdir: str | None = None,
    run_id: str | None = None,
    approval_status: str | None = Query(default=None, alias="status"),
):
    return _response(
        _interface(workdir).list_approvals(run_id=run_id, status=approval_status)
    )


@router.post("/approvals/{approval_id}/approve")
async def approve_runtime_request(
    approval_id: str,
    request: ApprovalDecisionRequest,
):
    response = {"approved": True, **request.response}
    return _response(_interface(request.workdir).approve(approval_id, response))


@router.post("/approvals/{approval_id}/reject")
async def reject_runtime_request(
    approval_id: str,
    request: ApprovalDecisionRequest,
):
    response = {"approved": False, **request.response}
    return _response(_interface(request.workdir).reject(approval_id, response))


@router.get("/artifacts/{artifact_id}")
async def get_runtime_artifact(artifact_id: str, workdir: str | None = None):
    return _response(_interface(workdir).get_artifact(artifact_id))


@router.get("/audit")
async def list_runtime_audit(
    workdir: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
):
    return _response(_interface(workdir).list_audit(actor_id=actor_id, action=action))
