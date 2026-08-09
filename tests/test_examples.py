"""Keep repository scenario demos executable as public API examples."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

OFFLINE_MODULES = (
    "examples.sdk_direct_tools",
    "examples.project_memory",
    "examples.skill_loading",
    "examples.mcp_stdio",
    "examples.runtime_events",
    "examples.workflow_parallel",
    "examples.multi_agent_team",
    "examples.approval_resume",
    "examples.quality_repair",
    "examples.runtime_retry_fork",
    "examples.sandbox_local",
    "examples.remote_sandbox_adapter",
    "examples.artifact_storage",
)

EXTERNAL_MODULES = (
    "examples.sdk_single_task",
    "examples.sdk_streaming_session",
    "examples.sdk_read_only_review",
    "examples.sdk_custom_tool",
    "examples.sdk_multimodal",
    "examples.sdk_interaction",
    "examples.container_sandbox",
    "examples.postgres_shared_state",
    "examples.web_runtime_client",
)


def run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CODY_")}
    with TemporaryDirectory(prefix="cody-example-home-") as home:
        env.update(
            {
                "HOME": home,
                "PYTHONPATH": str(ROOT),
                "XDG_CONFIG_HOME": str(Path(home) / ".config"),
            }
        )
        return subprocess.run(
            [sys.executable, "-m", module, *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def test_every_example_is_listed_in_the_demo_index():
    index = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    public_modules = {
        path.stem
        for path in EXAMPLES.glob("*.py")
        if path.stem not in {"__init__", "_support"}
    }
    assert public_modules == {module.rsplit(".", 1)[1] for module in (*OFFLINE_MODULES, *EXTERNAL_MODULES)}
    assert all(f"`{module}`" in index for module in public_modules)


@pytest.mark.parametrize("module", OFFLINE_MODULES)
def test_offline_scenario_demo_runs(module: str):
    result = run_module(module)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip()


@pytest.mark.parametrize("module", EXTERNAL_MODULES)
def test_external_scenario_demo_imports_and_exposes_help(module: str):
    result = run_module(module, "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout
