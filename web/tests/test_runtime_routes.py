from fastapi.testclient import TestClient

from cody.core.runtime import RuntimeStoreBundle
from tests.test_runtime_surfaces import seed_runtime
from web.backend.app import app
from web.backend.state import reset_state


def test_web_runtime_reads_state_seeded_for_same_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    runtime_home = tmp_path / "runtime-home"
    monkeypatch.setenv("CODY_RUNTIME_HOME", str(runtime_home))
    _, run, checkpoint, artifact, approval = seed_runtime(project, runtime_home)
    reset_state()

    with TestClient(app) as client:
        listed = client.get("/runtime/runs", params={"workdir": str(project)})
        assert listed.status_code == 200
        assert listed.json()["runs"][0]["run_id"] == run.run_id

        shown = client.get(
            f"/runtime/runs/{run.run_id}",
            params={"workdir": str(project)},
        )
        assert shown.status_code == 200
        assert shown.json()["steps"][0]["step_id"] == "step_shared"

        timeline = client.get(
            f"/runtime/runs/{run.run_id}/timeline",
            params={"workdir": str(project)},
        )
        assert timeline.status_code == 200
        assert timeline.json()["items"][0]["event"]["event_type"] == "run.completed"

        checkpoints = client.get(
            f"/runtime/runs/{run.run_id}/checkpoints",
            params={"workdir": str(project)},
        )
        assert checkpoints.json()["checkpoints"][0]["checkpoint_id"] == checkpoint.checkpoint_id

        artifacts = client.get(
            f"/runtime/runs/{run.run_id}/artifacts",
            params={"workdir": str(project)},
        )
        assert artifacts.json()["artifacts"][0]["artifact_id"] == artifact.artifact_id

        decision = client.post(
            f"/runtime/approvals/{approval.approval_id}/approve",
            json={"workdir": str(project), "response": {"source": "web"}},
        )
        assert decision.status_code == 200
        assert decision.json()["approval"]["status"] == "approved"

    reopened = RuntimeStoreBundle.for_workdir(project)
    assert reopened.approval_store.get(approval.approval_id).response["source"] == "web"
