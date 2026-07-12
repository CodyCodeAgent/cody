#!/usr/bin/env python3
"""Run non-destructive live Cody capability checks against an OpenAI API.

The API key is read only from ``CODY_LIVE_API_KEY`` and is never persisted or
included in the JSON report. The verifier uses a temporary workspace.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from typing import Awaitable, Callable
import sys

from pydantic_ai import RunContext
from pydantic_ai import Agent

from cody.core.config import Config, MCPServerConfig
from cody.core.deps import CodyDeps
from cody.core.runtime import (
    CodyRuntime,
    AgentRole,
    AsyncMultiAgentCoordinator,
    RunEventType,
    RuntimeStoreBundle,
    Workflow,
    WorkflowEdgeType,
    WorkflowNodeType,
    WorkflowWaiting,
    command_evaluator,
)
from cody.core.runner import AgentRunner
from cody.core.model_resolver import resolve_model
from cody.core.sub_agent import AgentStatus, SubAgentManager
from cody.sdk import AsyncCodyClient


@dataclass
class Check:
    name: str
    status: str
    duration_seconds: float
    evidence: dict[str, object]
    error: str | None = None


def live_config(workdir: Path, *, sandbox: bool = False, reasoner: bool = False) -> Config:
    key = os.environ.get("CODY_LIVE_API_KEY")
    if not key:
        raise RuntimeError("CODY_LIVE_API_KEY is required")
    config = Config(
        model="deepseek-reasoner" if reasoner else "deepseek-chat",
        model_base_url=os.environ.get("CODY_LIVE_BASE_URL", "https://api.deepseek.com"),
        model_api_key=key,
    )
    config.permissions.default_level = "allow"
    config.permissions.overrides = {
        "write_file": "allow",
        "edit_file": "allow",
        "patch": "allow",
        "exec_command": "allow",
        "spawn_agent": "allow",
        "kill_agent": "allow",
        "resume_agent": "allow",
        "mcp_call": "allow",
        "undo_file": "allow",
        "redo_file": "allow",
    }
    if sandbox:
        config.sandbox.enabled = True
        config.sandbox.backend = "seatbelt"
        config.sandbox.network_mode = "disabled"
        config.sandbox.fail_if_unavailable = True
        config.sandbox.state_root = str(workdir.parent / "sandbox-state")
    return config


def client_for(
    workdir: Path,
    *,
    sandbox: bool = False,
    reasoner: bool = False,
    custom_tools: list | None = None,
    before_tool_hooks: list | None = None,
    after_tool_hooks: list | None = None,
) -> AsyncCodyClient:
    client = AsyncCodyClient(
        workdir=str(workdir),
        custom_tools=custom_tools,
        before_tool_hooks=before_tool_hooks,
        after_tool_hooks=after_tool_hooks,
    )
    client._config.lsp.enabled = False  # verifier controls LSP separately
    client.set_config(live_config(workdir, sandbox=sandbox, reasoner=reasoner))
    return client


async def basic_sdk(workdir: Path) -> dict[str, object]:
    async with client_for(workdir) as client:
        result = await client.run(
            "Reply with exactly LIVE_BASIC_OK and no other text.",
            include_tools=[],
        )
        if "LIVE_BASIC_OK" not in result.output:
            raise AssertionError(f"unexpected output: {result.output[:200]}")
        if not result.run_id or result.usage.total_tokens <= 0:
            raise AssertionError("run_id or token usage missing")
        return {
            "run_id": result.run_id,
            "output": result.output.strip(),
            "tokens": result.usage.total_tokens,
        }


async def provider_stream_probe(workdir: Path) -> dict[str, object]:
    config = live_config(workdir)
    agent = Agent(resolve_model(config))
    seen: list[dict[str, object]] = []
    output = ""
    async with agent.iter("Reply exactly RAW_STREAM_OK") as run:
        async for node in run:
            if agent.is_model_request_node(node):
                async with node.stream(run.ctx) as stream:
                    async for event in stream:
                        part = getattr(event, "part", None)
                        delta = getattr(event, "delta", None)
                        seen.append(
                            {
                                "event": type(event).__name__,
                                "part_kind": getattr(part, "part_kind", None),
                                "part_type": type(part).__name__ if part is not None else None,
                                "delta_kind": getattr(delta, "part_delta_kind", None),
                                "delta_type": type(delta).__name__ if delta is not None else None,
                                "content": str(
                                    getattr(part, "content", None)
                                    or getattr(delta, "content_delta", None)
                                    or ""
                                ),
                            }
                        )
            if agent.is_end_node(node):
                output = str(run.result.output)
    if not seen or "RAW_STREAM_OK" not in output:
        raise AssertionError(f"raw provider stream missing: {seen}, {output}")
    return {"events": seen, "output": output}


async def streaming(workdir: Path) -> dict[str, object]:
    chunk_types: list[str] = []
    text = ""
    run_ids: set[str] = set()
    async with client_for(workdir) as client:
        async for chunk in client.stream(
            "Reply with exactly LIVE_STREAM_OK and no other text.",
            include_tools=[],
        ):
            chunk_types.append(chunk.type)
            text += chunk.content if chunk.type == "text_delta" else ""
            if chunk.run_id:
                run_ids.add(chunk.run_id)
    if "LIVE_STREAM_OK" not in text or "done" not in chunk_types:
        raise AssertionError(f"invalid stream: {chunk_types}, {text[:200]}")
    return {"chunk_types": chunk_types, "run_ids": sorted(run_ids), "text": text}


async def session_memory(workdir: Path) -> dict[str, object]:
    nonce = "CODY_SESSION_7391"
    async with client_for(workdir) as client:
        session = await client.create_session(title="live verifier")
        first = await client.run(
            f"Remember this exact nonce for the next turn: {nonce}. Reply ACK.",
            session_id=session.id,
            include_tools=[],
        )
        second = await client.run(
            "What exact nonce did I ask you to remember? Reply with only it.",
            session_id=session.id,
            include_tools=[],
        )
        if nonce not in second.output:
            raise AssertionError(f"session memory missing: {second.output[:200]}")
        detail = await client.get_session(session.id)
        return {
            "session_id": session.id,
            "first_run_id": first.run_id,
            "second_run_id": second.run_id,
            "message_count": len(detail.messages),
            "recalled": second.output.strip(),
        }


async def custom_tool_and_hooks(workdir: Path) -> dict[str, object]:
    calls: list[tuple[str, dict]] = []
    after_calls: list[str] = []

    async def live_probe(_ctx: RunContext[CodyDeps], value: str) -> str:
        """Return a deterministic live verification marker for the supplied value."""

        return f"PROBE_RESULT::{value.upper()}"

    async def before(name: str, args: dict) -> dict:
        calls.append((name, dict(args)))
        return args

    async def after(name: str, _args: dict, result: str) -> str:
        after_calls.append(name)
        return result + "::AFTER_HOOK"

    async with client_for(
        workdir,
        custom_tools=[live_probe],
        before_tool_hooks=[before],
        after_tool_hooks=[after],
    ) as client:
        result = await client.run(
            "You must call live_probe exactly once with value='alpha'. "
            "Then reply with the complete tool result and nothing else.",
            include_tools=["live_probe"],
        )
    if calls != [("live_probe", {"value": "alpha"})]:
        raise AssertionError(f"before hook/tool call mismatch: {calls}")
    if after_calls != ["live_probe"] or "AFTER_HOOK" not in result.output:
        raise AssertionError(f"after hook missing: {after_calls}, {result.output[:200]}")
    return {"run_id": result.run_id, "calls": calls, "output": result.output}


async def interaction_model(workdir: Path) -> dict[str, object]:
    client = client_for(workdir)
    client._config.interaction.enabled = True
    seen: list[str] = []
    text = ""
    async with client:
        async for chunk in client.stream(
            "Call question exactly once with text='Choose the live marker' and "
            "options='alpha,beta'. After the user answers, reply exactly "
            "INTERACTION_OK:<answer>.",
            include_tools=["question"],
        ):
            seen.append(chunk.type)
            if chunk.type == "interaction_request":
                if not chunk.request_id or chunk.options != ["alpha", "beta"]:
                    raise AssertionError(f"invalid interaction request: {chunk}")
                await client.submit_interaction(
                    chunk.request_id,
                    action="answer",
                    content="beta",
                )
            elif chunk.type == "text_delta":
                text += chunk.content
    if "INTERACTION_OK:beta" not in text or "interaction_request" not in seen:
        raise AssertionError(f"interaction failed: events={seen}, text={text}")
    return {"chunk_types": seen, "output": text}


async def builder_events_metrics(workdir: Path) -> dict[str, object]:
    from cody.sdk import Cody

    key = os.environ["CODY_LIVE_API_KEY"]
    events: list[str] = []
    client = (
        Cody()
        .workdir(str(workdir))
        .model("deepseek-chat")
        .api_key(key)
        .base_url(os.environ.get("CODY_LIVE_BASE_URL", "https://api.deepseek.com"))
        .lsp_languages([])
        .enable_metrics()
        .extra_system_prompt(
            "For the builder verification request, output exactly BUILDER_LIVE_OK."
        )
        .on("run_start", lambda event: events.append(event.event_type.value))
        .on("run_end", lambda event: events.append(event.event_type.value))
        .build()
    )
    async with client:
        result = await client.run("Perform the builder verification request.", include_tools=[])
        metrics = client.get_metrics() or {}
    if (
        "BUILDER_LIVE_OK" not in result.output
        or events != ["run_start", "run_end"]
        or metrics.get("total_runs") != 1
        or int(metrics.get("total_tokens", 0)) <= 0
    ):
        raise AssertionError(
            f"builder/events/metrics failed: output={result.output}, "
            f"events={events}, metrics={metrics}"
        )
    return {"run_id": result.run_id, "events": events, "metrics": metrics}


async def sync_sdk(workdir: Path) -> dict[str, object]:
    def execute() -> tuple[str, int]:
        from cody.sdk import CodyClient

        client = CodyClient(
            workdir=str(workdir),
            model="deepseek-chat",
            api_key=os.environ["CODY_LIVE_API_KEY"],
            base_url=os.environ.get("CODY_LIVE_BASE_URL", "https://api.deepseek.com"),
        )
        client._async._config.lsp.enabled = False
        try:
            result = client.run("Reply exactly LIVE_SYNC_SDK_OK and no other text.")
            return result.output, result.usage.total_tokens
        finally:
            client.close()

    output, tokens = await asyncio.to_thread(execute)
    if "LIVE_SYNC_SDK_OK" not in output or tokens <= 0:
        raise AssertionError(f"sync SDK failed: output={output}, tokens={tokens}")
    return {"output": output, "tokens": tokens}


async def cancellation_model(workdir: Path) -> dict[str, object]:
    tool_started = asyncio.Event()

    async def slow_live_tool(_ctx: RunContext[CodyDeps]) -> str:
        """Wait long enough for the live cancellation check to interrupt this tool."""

        tool_started.set()
        await asyncio.sleep(60)
        return "TOO_LATE"

    cancel = asyncio.Event()
    async with client_for(workdir, custom_tools=[slow_live_tool]) as client:
        task = asyncio.create_task(
            client.run(
                "You must call slow_live_tool exactly once.",
                include_tools=["slow_live_tool"],
                cancel_event=cancel,
            )
        )
        await asyncio.wait_for(tool_started.wait(), timeout=30)
        started = time.monotonic()
        cancel.set()
        try:
            result = await asyncio.wait_for(task, timeout=10)
        except TimeoutError as exc:
            event_types = [
                event.event_type.value
                for event in client.get_runtime().stores.trace_store.list_events()
            ]
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise AssertionError(
                f"cancellation timed out: cancel_set={cancel.is_set()}, "
                f"events={event_types}"
            ) from exc
        elapsed = time.monotonic() - started
    if result.output != "(cancelled)" or elapsed >= 10:
        raise AssertionError(
            f"cancellation failed: output={result.output}, elapsed={elapsed}"
        )
    return {"output": result.output, "cancel_latency_seconds": elapsed}


async def circuit_breaker_model(workdir: Path) -> dict[str, object]:
    client = client_for(workdir)
    config = client._get_config()
    config.circuit_breaker.enabled = True
    config.circuit_breaker.max_tokens = 1
    seen: list[str] = []
    async with client:
        async for chunk in client.stream(
            "Reply exactly THIS_RESPONSE_MUST_TRIP_THE_TOKEN_BREAKER.",
            include_tools=[],
        ):
            seen.append(chunk.type)
    if "circuit_breaker" not in seen:
        raise AssertionError(f"circuit breaker event missing: {seen}")
    return {"chunk_types": seen}


async def structured_stateless_model(workdir: Path) -> dict[str, object]:
    from cody.core.storage import NullSessionStore
    from cody.sdk import Cody

    client = (
        Cody()
        .workdir(str(workdir))
        .model("deepseek-chat")
        .api_key(os.environ["CODY_LIVE_API_KEY"])
        .base_url(os.environ.get("CODY_LIVE_BASE_URL", "https://api.deepseek.com"))
        .lsp_languages([])
        .stateless()
        .build()
    )
    async with client:
        result = await client.run(
            "Reply exactly with two lines: first '<confidence>0.91</confidence>' "
            "and second 'STRUCTURED_STATELESS_OK'.",
            include_tools=[],
        )
        sessions = await client.list_sessions()
        store = client.get_session_store()
    if (
        not isinstance(store, NullSessionStore)
        or sessions
        or result.metadata is None
        or result.metadata.confidence != 0.91
        or "STRUCTURED_STATELESS_OK" not in result.output
    ):
        raise AssertionError(
            f"structured/stateless failed: store={type(store).__name__}, "
            f"sessions={sessions}, metadata={result.metadata}, output={result.output}"
        )
    return {
        "run_id": result.run_id,
        "store": type(store).__name__,
        "session_count": len(sessions),
        "confidence": result.metadata.confidence,
        "output": result.output,
    }


async def file_command_seatbelt(workdir: Path) -> dict[str, object]:
    async with client_for(workdir, sandbox=True) as client:
        result = await client.run(
            "Complete these steps using tools, without skipping any: "
            "(1) use write_file to create live_check.py containing exactly "
            "print('SANDBOX_TOOL_OK'); (2) use exec_command to run "
            "python3 live_check.py; (3) reply with the command output.",
            include_tools=["write_file", "exec_command", "read_file"],
        )
        runtime = client.get_runtime()
        events = runtime.stores.trace_store.list_events(result.run_id)
    created = workdir / "live_check.py"
    if not created.is_file() or "SANDBOX_TOOL_OK" not in result.output:
        raise AssertionError(f"file/command loop failed: {result.output[:300]}")
    event_types = [event.event_type.value for event in events]
    required = {
        RunEventType.SANDBOX_CREATED.value,
        RunEventType.SANDBOX_STARTED.value,
        RunEventType.SANDBOX_TERMINATED.value,
        RunEventType.TOOL_CALL_STARTED.value,
        RunEventType.TOOL_CALL_COMPLETED.value,
        RunEventType.RUN_COMPLETED.value,
    }
    missing = required.difference(event_types)
    if missing:
        raise AssertionError(f"missing canonical events: {sorted(missing)}")
    return {
        "run_id": result.run_id,
        "output": result.output,
        "event_types": event_types,
        "file_content": created.read_text(),
    }


async def reasoner(workdir: Path) -> dict[str, object]:
    async with client_for(workdir, reasoner=True) as client:
        result = await client.run(
            "Compute 17 * 19 and reply with exactly REASONER_OK:<answer>.",
            include_tools=[],
        )
    if "REASONER_OK:323" not in result.output.replace(" ", ""):
        raise AssertionError(f"reasoner output mismatch: {result.output[:200]}")
    return {
        "run_id": result.run_id,
        "output": result.output,
        "thinking_present": bool(result.thinking),
        "tokens": result.usage.total_tokens,
    }


async def deepseek_current_models(workdir: Path) -> dict[str, object]:
    outputs: dict[str, str] = {}
    for model_name, marker in (
        ("deepseek-v4-flash", "V4_FLASH_LIVE_OK"),
        ("deepseek-v4-pro", "V4_PRO_LIVE_OK"),
    ):
        config = live_config(workdir)
        config.model = model_name
        agent = Agent(resolve_model(config))
        result = await agent.run(f"Reply exactly {marker} and no other text.")
        output = str(result.output)
        if marker not in output:
            raise AssertionError(f"{model_name} failed: {output}")
        outputs[model_name] = output
    return {"outputs": outputs}


async def sub_agent(workdir: Path) -> dict[str, object]:
    manager = SubAgentManager(live_config(workdir), workdir, default_timeout=120)
    try:
        agent_id = await manager.spawn(
            "Reply with exactly LIVE_SUB_AGENT_OK and do not use tools.",
            "research",
        )
        result = await manager.wait(agent_id)
        resumed_id = await manager.resume(agent_id)
        resumed = await manager.wait(resumed_id)
    finally:
        await manager.cleanup()
    if (
        result.status != AgentStatus.COMPLETED
        or resumed.status != AgentStatus.COMPLETED
        or "LIVE_SUB_AGENT_OK" not in result.output
        or "LIVE_SUB_AGENT_OK" not in resumed.output
    ):
        raise AssertionError(f"sub-agent failed: {result.status}: {result.error}")
    return {
        "agent_id": agent_id,
        "status": result.status.value,
        "output": result.output,
        "resumed_agent_id": resumed_id,
        "resumed_status": resumed.status.value,
        "resumed_output": resumed.output,
    }


async def mcp_model(workdir: Path) -> dict[str, object]:
    client = client_for(workdir)
    client._auto_start_mcp = True
    config = client._get_config()
    server = Path(__file__).with_name("live_mcp_server.py").resolve()
    config.mcp.servers = [
        MCPServerConfig(
            name="live",
            transport="stdio",
            command=sys.executable,
            args=[str(server)],
        )
    ]
    # The runner is lazy; it must be created after the live MCP config is set.
    async with client:
        result = await client.run(
            "You must call mcp_call exactly once with tool_name='live/echo_marker' "
            "and arguments={'value':'beta'}. Reply with only its full result.",
            include_tools=["mcp_call", "mcp_list_tools"],
        )
        runner = client.get_runner()
        discovered = [tool.name for tool in runner._mcp_client.list_tools()]
    if "MCP_LIVE_OK::BETA" not in result.output or discovered != ["echo_marker"]:
        raise AssertionError(f"MCP model loop failed: {discovered}, {result.output[:300]}")
    return {"run_id": result.run_id, "tools": discovered, "output": result.output}


async def mcp_http_model(workdir: Path) -> dict[str, object]:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = int(reservation.getsockname()[1])
    server = Path(__file__).with_name("live_mcp_http_server.py").resolve()
    process = subprocess.Popen(
        [sys.executable, str(server), "--port", str(port)],
        cwd=workdir,
        env={"PATH": os.environ.get("PATH", "")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                del reader
                break
            except OSError:
                if process.poll() is not None:
                    raise AssertionError(
                        f"HTTP MCP fixture exited: {process.stderr.read()}"
                    )
                if time.monotonic() >= deadline:
                    raise TimeoutError("HTTP MCP fixture did not start")
                await asyncio.sleep(0.05)

        client = client_for(workdir)
        client._auto_start_mcp = True
        config = client._get_config()
        config.mcp.servers = [
            MCPServerConfig(
                name="live-http",
                transport="http",
                url=f"http://127.0.0.1:{port}/mcp",
            )
        ]
        async with client:
            result = await client.run(
                "Call mcp_call exactly once with tool_name='live-http/echo_marker' "
                "and arguments={'value':'gamma'}. Reply with only the full result.",
                include_tools=["mcp_call", "mcp_list_tools"],
            )
            discovered = [tool.name for tool in client.get_runner()._mcp_client.list_tools()]
        if "MCP_HTTP_LIVE_OK::GAMMA" not in result.output or discovered != ["echo_marker"]:
            raise AssertionError(
                f"HTTP MCP model loop failed: {discovered}, {result.output[:300]}"
            )
        return {"run_id": result.run_id, "tools": discovered, "output": result.output}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def lsp_model_seatbelt(workdir: Path) -> dict[str, object]:
    (workdir / "go.mod").write_text("module example.com/live\n\ngo 1.22\n")
    (workdir / "main.go").write_text(
        "package main\n\nfunc main() {\n\tmissingName()\n}\n"
    )
    cache = workdir / ".cache"
    cache.mkdir()
    client = client_for(workdir, sandbox=True)
    client._config.lsp.enabled = True
    client._config.lsp.languages = ["go"]
    config = client._get_config()
    config.sandbox.env = {
        "GOCACHE": str(cache / "go-build"),
        "GOPATH": str(cache / "gopath"),
    }
    async with client:
        result = await client.run(
            "You must call lsp_diagnostics exactly once for file_path='main.go'. "
            "Reply with only the complete diagnostic result.",
            include_tools=["lsp_diagnostics"],
        )
        runner = client.get_runner()
        running = runner._lsp_client.running_servers
        server = runner._lsp_client._servers.get("go")
        diagnostics = [
            str(item)
            for items in (server._diagnostics.values() if server is not None else [])
            for item in items
        ]
    joined = "\n".join(diagnostics)
    if (
        "missingName" not in result.output
        or "missingName" not in joined
        or "operation not permitted" in joined.lower()
        or running != ["go"]
    ):
        raise AssertionError(
            f"LSP model loop failed: {running}, {diagnostics}, {result.output[:300]}"
        )
    return {
        "run_id": result.run_id,
        "running_servers": running,
        "diagnostics": diagnostics,
        "output": result.output,
    }


async def webfetch_model(workdir: Path) -> dict[str, object]:
    async with client_for(workdir) as client:
        result = await client.run(
            "You must call webfetch exactly once with url='https://example.com'. "
            "Reply with the page title and no unrelated explanation.",
            include_tools=["webfetch"],
        )
    if "Example Domain" not in result.output:
        raise AssertionError(f"webfetch loop failed: {result.output[:300]}")
    return {"run_id": result.run_id, "output": result.output}


def _live_process_env() -> dict[str, str]:
    key = os.environ["CODY_LIVE_API_KEY"]
    return {
        **os.environ,
        "CODY_MODEL": "deepseek-chat",
        "CODY_MODEL_BASE_URL": os.environ.get(
            "CODY_LIVE_BASE_URL", "https://api.deepseek.com"
        ),
        "CODY_MODEL_API_KEY": key,
        "CODY_LSP_LANGUAGES": "",
    }


@contextmanager
def _applied_live_process_env(**extra: str):
    values = {**_live_process_env(), **extra}
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


async def cli_surface(workdir: Path) -> dict[str, object]:
    env = {
        **_live_process_env(),
        "CODY_RUNTIME_HOME": str(workdir / ".runtime-home"),
    }
    completed = await asyncio.to_thread(
        subprocess.run,
        [
            str(Path(sys.executable).parent / "cody"),
            "run",
            "Reply with exactly LIVE_CLI_OK and no other text.",
            "--workdir",
            str(workdir),
            "--include-tools",
            "",
        ],
        cwd=workdir,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    if completed.returncode != 0 or "LIVE_CLI_OK" not in combined:
        raise AssertionError(
            f"CLI failed rc={completed.returncode}: {combined[-1000:]}"
        )
    executable = str(Path(sys.executable).parent / "cody")

    async def query(*args: str) -> dict:
        response = await asyncio.to_thread(
            subprocess.run,
            [executable, *args, "--workdir", str(workdir), "--json"],
            cwd=workdir,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if response.returncode != 0:
            raise AssertionError(f"CLI {' '.join(args)} failed: {response.stderr}")
        return json.loads(response.stdout)

    listed = await query("runs", "list")
    runs = listed.get("runs") or []
    if len(runs) != 1:
        raise AssertionError(f"CLI run catalog mismatch: {listed}")
    run_id = str(runs[0]["run_id"])
    shown = await query("runs", "show", run_id)
    metrics = await query("runs", "metrics", run_id)
    timeline = await query("timeline", "show", run_id)
    artifacts = await query("artifacts", "list", "--run-id", run_id)
    if (
        shown.get("run", {}).get("status") != "completed"
        or not timeline.get("items")
        or not artifacts.get("artifacts")
        or metrics.get("metrics", {}).get("event_count", 0) <= 0
    ):
        raise AssertionError(
            f"CLI runtime inspection failed: {shown}, {metrics}, {timeline}, {artifacts}"
        )
    return {
        "returncode": completed.returncode,
        "run_id": run_id,
        "status": shown["run"]["status"],
        "timeline_items": len(timeline["items"]),
        "artifact_count": len(artifacts["artifacts"]),
        "output_tail": combined[-1000:],
    }


async def web_rest_surface(workdir: Path) -> dict[str, object]:
    def request() -> tuple[int, dict]:
        with _applied_live_process_env(
            CODY_RUNTIME_HOME=str(workdir / ".runtime-home")
        ):
            from fastapi.testclient import TestClient
            from web.backend.app import app

            response = TestClient(app).post(
                "/run",
                json={
                    "prompt": "Reply exactly LIVE_WEB_REST_OK and no other text.",
                    "workdir": str(workdir),
                    "include_tools": [],
                },
            )
            return response.status_code, response.json()

    status, body = await asyncio.to_thread(request)
    if status != 200 or "LIVE_WEB_REST_OK" not in str(body.get("output")):
        raise AssertionError(f"Web REST failed status={status}: {body}")
    return {"status_code": status, "output": body["output"], "usage": body.get("usage")}


async def web_sse_surface(workdir: Path) -> dict[str, object]:
    def request() -> tuple[int, list[dict]]:
        with _applied_live_process_env(
            CODY_RUNTIME_HOME=str(workdir / ".runtime-home")
        ):
            from fastapi.testclient import TestClient
            from web.backend.app import app

            with TestClient(app).stream(
                "POST",
                "/run/stream",
                json={
                    "prompt": "Reply exactly LIVE_WEB_SSE_OK and no other text.",
                    "workdir": str(workdir),
                    "include_tools": [],
                },
            ) as response:
                events = [
                    json.loads(line.removeprefix("data: "))
                    for line in response.iter_lines()
                    if line.startswith("data: ")
                ]
                return response.status_code, events

    status, events = await asyncio.to_thread(request)
    types = [str(event.get("type")) for event in events]
    rendered = json.dumps(events, ensure_ascii=False)
    if status != 200 or "LIVE_WEB_SSE_OK" not in rendered or "done" not in types:
        raise AssertionError(f"Web SSE failed status={status}: {events}")
    return {"status_code": status, "event_types": types, "marker_seen": True}


async def web_runtime_surface(workdir: Path) -> dict[str, object]:
    def request() -> dict[str, object]:
        with _applied_live_process_env(
            CODY_RUNTIME_HOME=str(workdir / ".runtime-home")
        ):
            from fastapi.testclient import TestClient
            from web.backend.app import app

            with TestClient(app) as client:
                started = client.post(
                    "/runtime/runs",
                    json={
                        "prompt": "Reply exactly LIVE_WEB_RUNTIME_OK and no other text.",
                        "workdir": str(workdir),
                    },
                )
                if started.status_code != 202:
                    raise AssertionError(f"runtime start failed: {started.text}")
                run_id = str(started.json()["run_id"])
                detail: dict = {}
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    response = client.get(
                        f"/runtime/runs/{run_id}", params={"workdir": str(workdir)}
                    )
                    detail = response.json()
                    if detail.get("run", {}).get("status") in {
                        "completed",
                        "failed",
                        "cancelled",
                        "waiting",
                    }:
                        break
                    time.sleep(0.05)
                timeline = client.get(
                    f"/runtime/runs/{run_id}/timeline",
                    params={"workdir": str(workdir)},
                ).json()
                metrics = client.get(
                    f"/runtime/runs/{run_id}/metrics",
                    params={"workdir": str(workdir)},
                ).json()
                artifacts = client.get(
                    f"/runtime/runs/{run_id}/artifacts",
                    params={"workdir": str(workdir)},
                ).json()
                listed = client.get(
                    "/runtime/runs", params={"workdir": str(workdir)}
                ).json()
                if (
                    detail.get("run", {}).get("status") != "completed"
                    or "LIVE_WEB_RUNTIME_OK"
                    not in json.dumps(artifacts, ensure_ascii=False)
                    or not timeline.get("items")
                    or metrics.get("metrics", {}).get("event_count", 0) <= 0
                    or not listed.get("runs")
                ):
                    raise AssertionError(
                        f"runtime API failed: {detail}, {timeline}, {metrics}, {artifacts}"
                    )
                return {
                    "run_id": run_id,
                    "status": detail["run"]["status"],
                    "timeline_items": len(timeline["items"]),
                    "artifact_count": len(artifacts["artifacts"]),
                }

    return await asyncio.to_thread(request)


async def web_websocket_surface(workdir: Path) -> dict[str, object]:
    def request() -> list[dict]:
        with _applied_live_process_env(
            CODY_RUNTIME_HOME=str(workdir / ".runtime-home")
        ):
            from fastapi.testclient import TestClient
            from cody.core.session import SessionStore
            from web.backend.app import app
            from web.backend.db import ProjectStore
            from web.backend.state import get_project_store, session_store_dep

            projects = ProjectStore(workdir / "web-projects.sqlite3")
            sessions = SessionStore(workdir / "web-sessions.sqlite3")
            app.dependency_overrides[get_project_store] = lambda: projects
            app.dependency_overrides[session_store_dep] = lambda: sessions
            try:
                with TestClient(app) as client:
                    created = client.post(
                        "/api/projects",
                        json={"name": "Live WS", "workdir": str(workdir)},
                    )
                    if created.status_code != 201:
                        raise AssertionError(f"project creation failed: {created.text}")
                    project_id = created.json()["id"]
                    received: list[dict] = []
                    with client.websocket_connect(f"/ws/chat/{project_id}") as ws:
                        ws.send_json(
                            {
                                "type": "message",
                                "content": "Reply exactly LIVE_WEB_WS_OK and no other text.",
                                "include_tools": [],
                            }
                        )
                        for _ in range(100):
                            event = ws.receive_json()
                            received.append(event)
                            if event.get("type") in {"done", "error"}:
                                break
                    return received
            finally:
                app.dependency_overrides.pop(get_project_store, None)
                app.dependency_overrides.pop(session_store_dep, None)
                sessions.close()

    events = await asyncio.to_thread(request)
    types = [str(event.get("type")) for event in events]
    rendered = json.dumps(events, ensure_ascii=False)
    if "LIVE_WEB_WS_OK" not in rendered or "done" not in types:
        raise AssertionError(f"WebSocket failed: {events}")
    return {"event_types": types, "marker_seen": True}


async def tui_surface(workdir: Path) -> dict[str, object]:
    from unittest.mock import patch

    from cody.tui.app import CodyTUI
    from cody.tui.widgets import MessageBubble

    config = live_config(workdir)
    app = CodyTUI(workdir=workdir)
    session_id = None
    with patch("cody.tui.app.Config.load", return_value=config):
        async with app.run_test(size=(100, 30)) as pilot:
            session_id = app._session_id
            if app._client is not None:
                app._client._config.lsp.enabled = False
            input_widget = app.query_one("#prompt-input")
            input_widget.value = "Reply exactly LIVE_TUI_OK and no other text."
            await pilot.press("enter")
            deadline = time.monotonic() + 120
            rendered = ""
            while time.monotonic() < deadline:
                await pilot.pause()
                rendered = "\n".join(
                    bubble.content_text
                    for bubble in app.query(MessageBubble)
                    if bubble.role == "assistant"
                )
                if "LIVE_TUI_OK" in rendered and not app.is_running:
                    break
                await asyncio.sleep(0.05)
            if (
                "LIVE_TUI_OK" not in rendered
                or app.is_running
                or app._total_tokens <= 0
            ):
                raise AssertionError(f"TUI live run failed: {rendered[-1000:]}")
            tokens = app._total_tokens
            if app._client is not None and session_id is not None:
                await app._client.delete_session(session_id)
    return {"session_created": bool(session_id), "tokens": tokens, "marker_seen": True}


async def approval_resume(workdir: Path) -> dict[str, object]:
    config = live_config(workdir, sandbox=True)
    config.permissions.overrides["write_file"] = "confirm"
    config.interaction.enabled = True
    stores = RuntimeStoreBundle.sqlite(workdir / ".runtime")
    first = CodyRuntime(
        AgentRunner(config=config, workdir=workdir), stores=stores, poll_interval=0
    )
    waiting = await first.start(
        "You must call write_file exactly once to create approved.txt with exact "
        "content APPROVAL_RESUME_OK. Then reply APPROVAL_RESUME_OK.",
        run_id="run_live_approval",
        include_tools=["write_file"],
    )
    try:
        await waiting.result()
    except WorkflowWaiting:
        pass
    else:
        raise AssertionError("run did not enter durable approval waiting")
    approvals = stores.approval_store.list(run_id=waiting.run_id)
    if len(approvals) != 1:
        raise AssertionError(f"expected one approval, got {len(approvals)}")
    first.approve(approvals[0].approval_id, {"action": "approve"})

    second = CodyRuntime(
        AgentRunner(config=config, workdir=workdir), stores=stores, poll_interval=0
    )
    resumed = await second.resume(waiting.run_id)
    try:
        result = await resumed.result()
    except WorkflowWaiting as exc:
        current = stores.approval_store.get(approvals[0].approval_id)
        raise AssertionError(
            f"resumed run waited again: approval={current.to_dict() if current else None}, "
            f"checkpoints={[item.to_dict() for item in stores.checkpoint_store.list_checkpoints(waiting.run_id)]}"
        ) from exc
    events = stores.trace_store.list_events(waiting.run_id)
    event_types = [event.event_type.value for event in events]
    snapshot_checkpoints = [
        checkpoint
        for checkpoint in stores.checkpoint_store.list_checkpoints(waiting.run_id)
        if checkpoint.metadata.get("sandbox_snapshot_artifact_id")
    ]
    snapshot_id = (
        snapshot_checkpoints[-1].metadata["sandbox_snapshot_artifact_id"]
        if snapshot_checkpoints
        else None
    )
    target = workdir / "approved.txt"
    required = {
        RunEventType.RUN_WAITING.value,
        RunEventType.SANDBOX_SNAPSHOT_CREATED.value,
        RunEventType.SANDBOX_RESUMED.value,
        RunEventType.RUN_COMPLETED.value,
    }
    if (
        not target.is_file()
        or target.read_text() != "APPROVAL_RESUME_OK"
        or not snapshot_id
        or not required.issubset(event_types)
    ):
        raise AssertionError(
            f"approval resume failed: file={target.exists()}, snapshot={snapshot_id}, "
            f"events={event_types}, output={result.output[:300]}"
        )
    return {
        "run_id": waiting.run_id,
        "approval_id": approvals[0].approval_id,
        "snapshot_artifact_id": snapshot_id,
        "event_types": event_types,
        "output": result.output,
    }


async def quality_repair_loop(workdir: Path) -> dict[str, object]:
    config = live_config(workdir, sandbox=True)
    runner = AgentRunner(config=config, workdir=workdir)
    workflow = (
        Workflow("live-quality-repair", workflow_id="workflow_live_quality")
        .node(
            "implement",
            WorkflowNodeType.AGENT,
            metadata={
                "prompt": (
                    "Use write_file to create result.txt containing exactly BROKEN. "
                    "Do not fix it yet."
                )
            },
        )
        .node(
            "gate",
            WorkflowNodeType.QUALITY_GATE,
            metadata={
                "max_repairs": 1,
                "quality_gate": {
                    "gate_id": "live_file_gate",
                    "metrics": [
                        {"metric_id": "tests", "threshold": 1.0, "required": True}
                    ],
                },
            },
        )
        .node(
            "repair",
            WorkflowNodeType.AGENT,
            metadata={
                "prompt": (
                    "The quality gate failed. Use write_file to replace result.txt "
                    "with exactly QUALITY_LIVE_OK."
                )
            },
        )
        .node("done", WorkflowNodeType.FUNCTION)
        .edge("implement", "gate")
        .edge("gate", "done")
        .edge(
            "gate",
            "repair",
            edge_type=WorkflowEdgeType.FALLBACK,
            metadata={"allow_revisit": True},
        )
        .edge("repair", "gate", metadata={"allow_revisit": True})
        .compile()
    )

    async def done(_state, _node):
        return {"delivered": True}

    evaluator = command_evaluator(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; assert Path('result.txt').read_text() == 'QUALITY_LIVE_OK'",
        ],
        workdir=workdir,
        timeout=20,
    )
    runtime = CodyRuntime(
        runner,
        quality_evaluators={"tests": evaluator},
        node_handlers={"function": done},
        poll_interval=0,
    )
    handle = await runtime.start(
        workflow,
        {"task": "Exercise the bounded quality repair loop."},
        run_id="run_live_quality",
    )
    result = await handle.result()
    event_types = [event.event_type.value for event in runtime.stores.trace_store.list_events(handle.run_id)]
    target = workdir / "result.txt"
    attempts = result.state.data.get("quality_gate_attempts")
    if (
        not target.is_file()
        or target.read_text() != "QUALITY_LIVE_OK"
        or attempts != {"live_file_gate": 2}
        or RunEventType.QUALITY_GATE_FAILED.value not in event_types
        or RunEventType.QUALITY_GATE_PASSED.value not in event_types
    ):
        raise AssertionError(
            f"quality repair failed: content={target.read_text() if target.exists() else None}, "
            f"attempts={attempts}, events={event_types}"
        )
    return {
        "run_id": handle.run_id,
        "attempts": attempts,
        "content": target.read_text(),
        "quality_events": [item for item in event_types if item.startswith("quality_gate.")],
    }


async def multi_agent_team(workdir: Path) -> dict[str, object]:
    active = 0
    max_active = 0

    async def backend(task, state):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            prior = json.dumps(state.data.get("agent_outputs") or {}, sort_keys=True)
            async with client_for(workdir) as client:
                result = await client.run(
                    f"{task.prompt}\nPrior agent outputs: {prior}\n"
                    "Follow the requested exact response format.",
                    include_tools=[],
                )
            return {"text": result.output, "run_id": result.run_id}
        finally:
            active -= 1

    coordinator = AsyncMultiAgentCoordinator(max_concurrency=2)
    coordinator.register_agent(
        AgentRole("deepseek-specialist", capabilities=frozenset({"live"})),
        backend,
    )
    workflow = (
        Workflow("live-agent-team", workflow_id="workflow_live_team")
        .node(
            "team",
            WorkflowNodeType.AGENT_TEAM,
            metadata={
                "agent_tasks": [
                    {
                        "task_id": "alpha",
                        "prompt": "Reply exactly TEAM_ALPHA_OK",
                        "required_capabilities": ["live"],
                    },
                    {
                        "task_id": "beta",
                        "prompt": "Reply exactly TEAM_BETA_OK",
                        "required_capabilities": ["live"],
                    },
                    {
                        "task_id": "review",
                        "prompt": (
                            "Verify prior outputs contain TEAM_ALPHA_OK and TEAM_BETA_OK; "
                            "reply exactly TEAM_REVIEW_OK"
                        ),
                        "required_capabilities": ["live"],
                        "depends_on": ["alpha", "beta"],
                    },
                ]
            },
        )
        .compile()
    )
    runtime = CodyRuntime(
        object(),
        multi_agent_coordinator=coordinator,
        max_concurrency=2,
        poll_interval=0,
    )
    handle = await runtime.start(workflow, run_id="run_live_team")
    result = await handle.result()
    outputs = result.state.data.get("agent_outputs") or {}
    rendered = json.dumps(outputs, sort_keys=True)
    if (
        max_active != 2
        or "TEAM_ALPHA_OK" not in rendered
        or "TEAM_BETA_OK" not in rendered
        or "TEAM_REVIEW_OK" not in rendered
    ):
        raise AssertionError(f"multi-agent team failed: max_active={max_active}, {rendered}")
    return {
        "run_id": handle.run_id,
        "max_parallel_agents": max_active,
        "outputs": outputs,
        "artifact_count": len(runtime.stores.artifact_store.list(run_id=handle.run_id)),
    }


async def direct_sdk_tools(workdir: Path) -> dict[str, object]:
    async with client_for(workdir) as client:
        await client.write_file("notes.txt", "alpha marker\n")
        await client.edit_file("notes.txt", "alpha", "beta")
        content = await client.read_file("notes.txt")
        listing = await client.list_directory(".")
        grep = await client.grep("beta", include="*.txt")
        glob = await client.glob("**/*.txt")
        search = await client.search_files("notes")
        command = await client.exec_command("python3 -c \"print('DIRECT_COMMAND_OK')\"")
    evidence = "\n".join((content, listing, grep, glob, search, command))
    required = ("beta marker", "notes.txt", "DIRECT_COMMAND_OK")
    if not all(marker in evidence for marker in required):
        raise AssertionError(f"direct SDK tools failed: {evidence[:1000]}")
    return {
        "content": content,
        "grep": grep,
        "glob": glob,
        "search": search,
        "command": command,
    }


async def skill_model(workdir: Path) -> dict[str, object]:
    skill_dir = workdir / ".cody" / "skills" / "live-verifier"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: live-verifier\n"
        "description: Supplies the exact marker required by the live capability check.\n"
        "---\n"
        "When asked for the live skill marker, reply exactly LIVE_SKILL_OK.\n"
    )
    async with client_for(workdir) as client:
        skills = await client.list_skills()
        detail = await client.get_skill("live-verifier")
        result = await client.run(
            "Use the live-verifier skill. You must call read_skill exactly once with "
            "skill_name='live-verifier', follow its instructions, and return only its marker.",
            include_tools=["read_skill", "list_skills"],
        )
    names = [str(skill["name"]) for skill in skills]
    if (
        "live-verifier" not in names
        or "LIVE_SKILL_OK" not in result.output
        or "LIVE_SKILL_OK" not in str(detail["documentation"])
    ):
        raise AssertionError(
            f"skill model loop failed: names={names}, output={result.output[:300]}"
        )
    return {
        "run_id": result.run_id,
        "skill_source": detail["source"],
        "skill_enabled": detail["enabled"],
        "output": result.output,
    }


async def stateful_tools_model(workdir: Path) -> dict[str, object]:
    async with client_for(workdir) as client:
        try:
            result = await client.run(
                "Execute every numbered step using the named tool, in order: "
                "1) write_file state.txt with exact content ONE followed by a newline; "
                "2) edit_file replacing ONE with TWO; 3) undo_file; 4) read_file and verify ONE; "
                "5) redo_file; 6) read_file and verify TWO; 7) patch state.txt using a valid "
                "unified diff that changes TWO to THREE; 8) list_file_changes; "
                "9) todo_write with one completed item named live-todo, then todo_read; "
                "10) save_memory category conventions with content LIVE_MEMORY_OK. "
                "After all steps succeed, reply exactly STATEFUL_TOOLS_OK.",
                include_tools=[
                    "write_file",
                    "edit_file",
                    "read_file",
                    "patch",
                    "undo_file",
                    "redo_file",
                    "list_file_changes",
                    "todo_write",
                    "todo_read",
                    "save_memory",
                ],
            )
        except WorkflowWaiting as exc:
            approvals = client.get_runtime().stores.approval_store.list()
            raise AssertionError(
                f"unexpected approval wait: {[item.to_dict() for item in approvals]}"
            ) from exc
        memory = await client.get_memory()
        events = client.get_runtime().stores.trace_store.list_events(result.run_id)
    tool_names = [
        str(event.payload.get("tool_name"))
        for event in events
        if event.event_type == RunEventType.TOOL_CALL_COMPLETED
    ]
    expected_tools = {
        "write_file",
        "edit_file",
        "read_file",
        "patch",
        "undo_file",
        "redo_file",
        "list_file_changes",
        "todo_write",
        "todo_read",
        "save_memory",
    }
    memory_text = json.dumps(memory, ensure_ascii=False)
    if (
        (workdir / "state.txt").read_text() != "THREE\n"
        or "LIVE_MEMORY_OK" not in memory_text
        or "STATEFUL_TOOLS_OK" not in result.output
        or not expected_tools.issubset(tool_names)
    ):
        raise AssertionError(
            f"stateful tools failed: tools={tool_names}, memory={memory_text}, "
            f"output={result.output[:300]}"
        )
    return {
        "run_id": result.run_id,
        "tool_names": tool_names,
        "file_content": (workdir / "state.txt").read_text(),
        "memory_saved": "LIVE_MEMORY_OK" in memory_text,
        "output": result.output,
    }


async def websearch_model(workdir: Path) -> dict[str, object]:
    async with client_for(workdir) as client:
        result = await client.run(
            "Call websearch exactly once with query='Python programming language'. "
            "Reply with WEBSEARCH_OK followed by the title of one returned result.",
            include_tools=["websearch"],
        )
        events = client.get_runtime().stores.trace_store.list_events(result.run_id)
    calls = [
        event.payload.get("tool_name")
        for event in events
        if event.event_type == RunEventType.TOOL_CALL_COMPLETED
    ]
    tool_results = [
        str(event.payload.get("result") or "")
        for event in events
        if event.event_type == RunEventType.TOOL_CALL_COMPLETED
        and event.payload.get("tool_name") == "websearch"
    ]
    if (
        "websearch" not in calls
        or not any("Search results for:" in item for item in tool_results)
        or "WEBSEARCH_OK" not in result.output
    ):
        raise AssertionError(
            f"websearch failed: calls={calls}, results={tool_results}, "
            f"output={result.output[:300]}"
        )
    return {
        "run_id": result.run_id,
        "calls": calls,
        "result_preview": tool_results[-1][:300],
        "output": result.output,
    }


async def lsp_navigation_model(workdir: Path) -> dict[str, object]:
    (workdir / "go.mod").write_text("module example.com/navigation\n\ngo 1.22\n")
    (workdir / "main.go").write_text(
        "package main\n\nfunc liveTarget() int { return 42 }\n\n"
        "func main() { _ = liveTarget() }\n"
    )
    cache = workdir / ".cache"
    cache.mkdir()
    client = client_for(workdir, sandbox=True)
    client._config.lsp.enabled = True
    client._config.lsp.languages = ["go"]
    client._get_config().sandbox.env = {
        "GOCACHE": str(cache / "go-build"),
        "GOPATH": str(cache / "gopath"),
    }
    async with client:
        result = await client.run(
            "Use all three LSP tools on the liveTarget call in main.go at line 5, "
            "zero-based character 18: "
            "lsp_definition, lsp_references, and lsp_hover. After they all return, "
            "reply exactly LSP_NAVIGATION_OK.",
            include_tools=["lsp_definition", "lsp_references", "lsp_hover"],
        )
        events = client.get_runtime().stores.trace_store.list_events(result.run_id)
    calls = {
        str(event.payload.get("tool_name"))
        for event in events
        if event.event_type == RunEventType.TOOL_CALL_COMPLETED
    }
    expected = {"lsp_definition", "lsp_references", "lsp_hover"}
    tool_results = [
        str(event.payload.get("result") or "")
        for event in events
        if event.event_type == RunEventType.TOOL_CALL_COMPLETED
    ]
    rendered = "\n".join(tool_results)
    if (
        not expected.issubset(calls)
        or "Definition: main.go:3" not in rendered
        or "References" not in rendered
        or "liveTarget" not in rendered
        or "LSP_NAVIGATION_OK" not in result.output
    ):
        raise AssertionError(
            f"LSP navigation failed: calls={calls}, results={tool_results}, "
            f"output={result.output[:300]}"
        )
    return {
        "run_id": result.run_id,
        "calls": sorted(calls),
        "tool_results": tool_results,
        "output": result.output,
    }


async def lsp_python_typescript(workdir: Path) -> dict[str, object]:
    typescript_package = Path(
        os.environ.get(
            "CODY_LIVE_TYPESCRIPT_PACKAGE",
            "/tmp/cody-lsp-live/node_modules/typescript",
        )
    )
    if not typescript_package.is_dir():
        raise RuntimeError(
            "Install TypeScript and set CODY_LIVE_TYPESCRIPT_PACKAGE for this check"
        )
    node_modules = workdir / "node_modules"
    node_modules.mkdir()
    (node_modules / "typescript").symlink_to(typescript_package, target_is_directory=True)
    (workdir / "main.py").write_text(
        "def py_target() -> int:\n    return 7\n\npy_value = py_target()\n"
    )
    (workdir / "main.ts").write_text(
        "function tsTarget(): number { return 8; }\n\nconst tsValue = tsTarget();\n"
    )
    (workdir / "tsconfig.json").write_text(
        '{"compilerOptions":{"strict":true,"noEmit":true},"include":["main.ts"]}\n'
    )
    client = client_for(workdir)
    client._config.lsp.enabled = True
    client._config.lsp.languages = ["python", "typescript"]
    ts_process = None
    ts_server = None
    async with client:
        await client.start_lsp()
        running = sorted(client.get_runner()._lsp_client.running_servers)
        ts_server = client.get_runner()._lsp_client._servers.get("typescript")
        ts_process = ts_server._process if ts_server is not None else None
        py_diagnostics = await client.lsp_diagnostics("main.py")
        ts_diagnostics = await client.lsp_diagnostics("main.ts")
        py_definition = await client.lsp_definition("main.py", 4, 11)
        py_hover = await client.lsp_hover("main.py", 4, 11)
        py_references = await client.lsp_references("main.py", 4, 11)
        ts_definition = await client.lsp_definition("main.ts", 3, 16)
        ts_hover = await client.lsp_hover("main.ts", 3, 16)
        ts_references = await client.lsp_references("main.ts", 3, 16)
        result = await client.run(
            "Reply exactly LSP_PY_TS_LIVE_OK and no other text.", include_tools=[]
        )
    ts_stderr = ""
    if ts_process is not None and ts_process.stderr is not None:
        ts_stderr = (await ts_process.stderr.read()).decode(errors="replace")
    evidence = "\n".join(
        (
            py_definition,
            py_diagnostics,
            py_hover,
            py_references,
            ts_definition,
            ts_diagnostics,
            ts_hover,
            ts_references,
        )
    )
    if (
        running != ["python", "typescript"]
        or "main.py:1" not in py_definition
        or "py_target" not in evidence
        or "main.ts:1" not in ts_definition
        or "tsTarget" not in evidence
        or "LSP_PY_TS_LIVE_OK" not in result.output
    ):
        raise AssertionError(
            f"Python/TypeScript LSP failed: running={running}, evidence={evidence}, "
            f"output={result.output}, ts_errors="
            f"{ts_server._response_errors if ts_server else []}, "
            f"ts_stderr={ts_stderr[-2000:]}"
        )
    return {
        "run_id": result.run_id,
        "running_servers": running,
        "python_definition": py_definition,
        "typescript_definition": ts_definition,
        "output": result.output,
    }


CASES: dict[str, Callable[[Path], Awaitable[dict[str, object]]]] = {
    "basic_sdk": basic_sdk,
    "provider_stream_probe": provider_stream_probe,
    "streaming": streaming,
    "session_memory": session_memory,
    "custom_tool_and_hooks": custom_tool_and_hooks,
    "interaction_model": interaction_model,
    "builder_events_metrics": builder_events_metrics,
    "sync_sdk": sync_sdk,
    "cancellation_model": cancellation_model,
    "circuit_breaker_model": circuit_breaker_model,
    "structured_stateless_model": structured_stateless_model,
    "file_command_seatbelt": file_command_seatbelt,
    "reasoner": reasoner,
    "deepseek_current_models": deepseek_current_models,
    "sub_agent": sub_agent,
    "mcp_model": mcp_model,
    "mcp_http_model": mcp_http_model,
    "lsp_model_seatbelt": lsp_model_seatbelt,
    "webfetch_model": webfetch_model,
    "cli_surface": cli_surface,
    "web_rest_surface": web_rest_surface,
    "web_sse_surface": web_sse_surface,
    "web_runtime_surface": web_runtime_surface,
    "web_websocket_surface": web_websocket_surface,
    "tui_surface": tui_surface,
    "approval_resume": approval_resume,
    "quality_repair_loop": quality_repair_loop,
    "multi_agent_team": multi_agent_team,
    "direct_sdk_tools": direct_sdk_tools,
    "skill_model": skill_model,
    "stateful_tools_model": stateful_tools_model,
    "websearch_model": websearch_model,
    "lsp_navigation_model": lsp_navigation_model,
    "lsp_python_typescript": lsp_python_typescript,
}


async def run(selected: list[str]) -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory(prefix="cody-live-") as root_text:
        root = Path(root_text)
        for name in selected:
            workdir = root / name
            workdir.mkdir()
            started = time.monotonic()
            try:
                evidence = await CASES[name](workdir)
                checks.append(Check(name, "passed", time.monotonic() - started, evidence))
            except Exception as exc:  # continue to gather the whole live matrix
                checks.append(
                    Check(name, "failed", time.monotonic() - started, {}, f"{type(exc).__name__}: {exc}")
                )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="*", choices=sorted(CASES))
    args = parser.parse_args()
    selected = args.cases or list(CASES)
    checks = asyncio.run(run(selected))
    print(json.dumps([asdict(check) for check in checks], ensure_ascii=False, indent=2))
    return 0 if all(check.status == "passed" for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
