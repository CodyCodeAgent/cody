"""Canonical Runtime inspection and control commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

import click

from ...core import Config
from ...core.runtime import (
    CodyRuntime,
    RunStatus,
    RuntimeAPIResponse,
    RuntimeStoreBundle,
)
from ..utils import _ensure_config_ready, console


def _interface(workdir: str | None):
    path = Path(workdir).expanduser().resolve() if workdir else Path.cwd()
    return RuntimeStoreBundle.for_workdir(path).interface()


def _emit(response, *, as_json: bool) -> None:
    if not response.ok:
        raise click.ClickException(response.error or "Runtime action failed")
    if as_json:
        click.echo(json.dumps(response.data, ensure_ascii=False, indent=2))
        return
    console.print_json(data=response.data)


@click.group()
def runs():
    """Inspect and control canonical Runtime runs."""


@runs.command("list")
@click.option("--status", type=click.Choice([status.value for status in RunStatus]))
@click.option("--limit", default=20, show_default=True, type=click.IntRange(1, 1000))
@click.option("--offset", default=0, show_default=True, type=click.IntRange(0))
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def runs_list(status, limit, offset, workdir, as_json):
    """List runs for a project."""

    _emit(
        _interface(workdir).list_runs(status=status, limit=limit, offset=offset),
        as_json=as_json,
    )


@runs.command("show")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def runs_show(run_id, workdir, as_json):
    """Show one run and its durable steps."""

    interface = _interface(workdir)
    run_response = interface.get_run(run_id)
    if not run_response.ok:
        _emit(run_response, as_json=as_json)
        return
    steps = interface.list_steps(run_id)
    data = {**run_response.data, **(steps.data if steps.ok else {})}
    _emit(RuntimeAPIResponse(ok=True, data=data), as_json=as_json)


@runs.command("metrics")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def runs_metrics(run_id, workdir, as_json):
    """Show duration, usage, retries, tools, gates, and artifact counts."""

    _emit(_interface(workdir).get_metrics(run_id), as_json=as_json)


@runs.command("watch")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--follow/--no-follow", default=True, show_default=True)
@click.option("--poll-interval", default=0.5, type=click.FloatRange(min=0.05))
@click.option("--json", "as_json", is_flag=True)
def runs_watch(run_id, workdir, follow, poll_interval, as_json):
    """Print canonical events, optionally following until a terminal state."""

    interface = _interface(workdir)
    index = 0
    while True:
        events = interface.replay(run_id).data.get("events", [])
        for event in events[index:]:
            click.echo(
                json.dumps(event, ensure_ascii=False)
                if as_json
                else f"{event['timestamp']} {event['event_type']} {event.get('step_id') or '-'}"
            )
        index = len(events)
        run_response = interface.get_run(run_id)
        if not run_response.ok:
            _emit(run_response, as_json=as_json)
            return
        status = run_response.data["run"].get("status")
        if not follow or status in {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
            RunStatus.WAITING.value,
            RunStatus.PAUSED.value,
        }:
            return
        time.sleep(poll_interval)


@runs.command("resume")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def runs_resume(run_id, workdir):
    """Resume a waiting or paused run from its latest checkpoint."""

    _run_async_control("resume", run_id=run_id, workdir=workdir)


@runs.command("cancel")
@click.argument("run_id")
@click.option("--before-node-id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def runs_cancel(run_id, before_node_id, workdir):
    """Request cancellation, including for a Run owned by another process."""

    _emit(
        _interface(workdir).request_cancel(
            run_id,
            before_node_id=before_node_id,
        ),
        as_json=False,
    )


@runs.command("pause")
@click.argument("run_id")
@click.option("--before-node-id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def runs_pause(run_id, before_node_id, workdir):
    """Request pause at the next safe node boundary."""

    _emit(
        _interface(workdir).request_pause(
            run_id,
            before_node_id=before_node_id,
        ),
        as_json=False,
    )


@runs.command("retry")
@click.argument("run_id")
@click.option("--checkpoint-id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def runs_retry(run_id, checkpoint_id, workdir):
    """Retry a failed or cancelled run."""

    _run_async_control(
        "retry",
        run_id=run_id,
        checkpoint_id=checkpoint_id,
        workdir=workdir,
    )


@runs.command("recover")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def runs_recover(run_id, workdir):
    """Recover a Run left running by a terminated process."""

    _run_async_control("recover", run_id=run_id, workdir=workdir)


@runs.command("fork")
@click.argument("checkpoint_id")
@click.option("--new-run-id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def runs_fork(checkpoint_id, new_run_id, workdir):
    """Fork and start a child run from a historical checkpoint."""

    _run_async_control(
        "fork",
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id,
        workdir=workdir,
    )


def _run_async_control(action: str, *, workdir: str | None, **kwargs: Any) -> None:
    path = Path(workdir).expanduser().resolve() if workdir else Path.cwd()
    config = _ensure_config_ready(Config.load(workdir=path))
    stores = RuntimeStoreBundle.for_workdir(path)

    async def execute() -> None:
        async with CodyRuntime.from_config(config, path, stores=stores) as runtime:
            observed_run_id = kwargs.get("run_id")
            before = (
                len(stores.trace_store.list_events(observed_run_id))
                if observed_run_id is not None
                else 0
            )
            operation = getattr(runtime, action)
            handle = await operation(**kwargs)
            async for event in handle.events(from_index=before):
                if event.event_type.value == "model.text.delta":
                    console.print(event.payload.get("content", ""), end="")
            result = await handle.result()
            console.print()
            console.print(f"[green]{result.run.status.value}[/green] {result.run.run_id}")

    asyncio.run(execute())


@click.group()
def approvals():
    """Inspect and decide durable Runtime approvals."""


@approvals.command("list")
@click.option("--run-id")
@click.option("--status", type=click.Choice(["pending", "approved", "rejected", "expired"]))
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def approvals_list(run_id, status, workdir, as_json):
    _emit(
        _interface(workdir).list_approvals(run_id=run_id, status=status),
        as_json=as_json,
    )


@approvals.command("approve")
@click.argument("approval_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def approvals_approve(approval_id, workdir):
    _emit(
        _interface(workdir).approve(approval_id, {"approved": True}),
        as_json=False,
    )


@approvals.command("reject")
@click.argument("approval_id")
@click.option("--reason")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
def approvals_reject(approval_id, reason, workdir):
    _emit(
        _interface(workdir).reject(
            approval_id,
            {"approved": False, "reason": reason},
        ),
        as_json=False,
    )


@click.group()
def artifacts():
    """Inspect Runtime artifacts."""


@artifacts.command("list")
@click.option("--run-id")
@click.option("--step-id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def artifacts_list(run_id, step_id, workdir, as_json):
    _emit(
        _interface(workdir).list_artifacts(run_id=run_id, step_id=step_id),
        as_json=as_json,
    )


@artifacts.command("show")
@click.argument("artifact_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def artifacts_show(artifact_id, workdir, as_json):
    _emit(_interface(workdir).get_artifact(artifact_id), as_json=as_json)


@click.group()
def timeline():
    """Inspect Runtime timelines and checkpoints."""


@timeline.command("show")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def timeline_show(run_id, workdir, as_json):
    _emit(_interface(workdir).get_timeline(run_id), as_json=as_json)


@timeline.command("checkpoints")
@click.argument("run_id")
@click.option("--workdir", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def timeline_checkpoints(run_id, workdir, as_json):
    _emit(_interface(workdir).list_checkpoints(run_id), as_json=as_json)
