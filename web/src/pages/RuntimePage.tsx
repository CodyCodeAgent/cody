import { useCallback, useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import {
  controlRuntimeRun,
  decideRuntimeApproval,
  getRuntimeMetrics,
  getRuntimeRun,
  getRuntimeTimeline,
  listProjects,
  listRuntimeApprovals,
  listRuntimeArtifacts,
  listRuntimeRuns,
  startRuntimeRun,
} from "../api/client";
import type {
  Project,
  RuntimeApproval,
  RuntimeArtifact,
  RuntimeEvent,
  RuntimeRun,
} from "../types";

function metricEntries(metrics: Record<string, unknown>): [string, unknown][] {
  return Object.entries(metrics).flatMap(([key, value]) => {
    if (key === "usage" && value && typeof value === "object") {
      return Object.entries(value as Record<string, unknown>);
    }
    return typeof value === "object" ? [] : [[key, value] as [string, unknown]];
  });
}

export default function RuntimePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [workdir, setWorkdir] = useState("");
  const [runs, setRuns] = useState<RuntimeRun[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<RuntimeRun | null>(null);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [artifacts, setArtifacts] = useState<RuntimeArtifact[]>([]);
  const [approvals, setApprovals] = useState<RuntimeApproval[]>([]);
  const [metrics, setMetrics] = useState<Record<string, unknown>>({});
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listProjects().then((items) => {
      setProjects(items);
      if (items[0]) setWorkdir(items[0].workdir);
    }).catch((e) => setError(String(e)));
  }, []);

  const refresh = useCallback(async () => {
    if (!workdir) return;
    try {
      const listed = await listRuntimeRuns(workdir);
      setRuns(listed.runs);
      const runId = selectedId || listed.runs[0]?.run_id;
      if (!runId) return;
      if (!selectedId) setSelectedId(runId);
      const [run, timeline, metricData, artifactData, approvalData] = await Promise.all([
        getRuntimeRun(runId, workdir),
        getRuntimeTimeline(runId, workdir),
        getRuntimeMetrics(runId, workdir),
        listRuntimeArtifacts(runId, workdir),
        listRuntimeApprovals(runId, workdir),
      ]);
      setSelected(run.run);
      setEvents(timeline.events || []);
      setMetrics(metricData.metrics || {});
      setArtifacts(artifactData.artifacts || []);
      setApprovals(approvalData.approvals || []);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [workdir, selectedId]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function startRun() {
    if (!prompt.trim() || !workdir) return;
    const created = await startRuntimeRun(prompt.trim(), workdir);
    setPrompt("");
    setSelectedId(created.run_id);
  }

  async function control(action: "cancel" | "pause" | "resume" | "retry") {
    if (!selectedId) return;
    await controlRuntimeRun(selectedId, action, workdir);
    await refresh();
  }

  return (
    <div className="chat-page">
      <Sidebar />
      <main className="chat-main runtime-console">
        <header className="runtime-header">
          <div><h2>Agent Runtime</h2><p>Runs, approvals, timeline, artifacts, cost and quality.</p></div>
          <select aria-label="Runtime project" value={workdir} onChange={(e) => { setWorkdir(e.target.value); setSelectedId(""); }}>
            {projects.map((project) => <option key={project.id} value={project.workdir}>{project.name}</option>)}
          </select>
        </header>
        <div className="runtime-start">
          <input aria-label="Runtime prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Start a durable agent run…" />
          <button className="btn btn-primary" onClick={startRun}>Run</button>
        </div>
        {error && <div className="error-message">{error}</div>}
        <div className="runtime-grid">
          <section className="runtime-panel runtime-run-list">
            <h3>Runs</h3>
            {runs.map((run) => (
              <button key={run.run_id} className={`runtime-run ${selectedId === run.run_id ? "active" : ""}`} onClick={() => setSelectedId(run.run_id)}>
                <span>{run.task}</span><small>{run.status} · {run.run_id.slice(0, 12)}</small>
              </button>
            ))}
          </section>
          <section className="runtime-panel runtime-detail">
            <div className="runtime-title"><h3>{selected?.task || "Select a run"}</h3><span className={`runtime-status status-${selected?.status}`}>{selected?.status}</span></div>
            {selected && <div className="runtime-actions">
              <button className="btn btn-sm" onClick={() => control("pause")}>Pause</button>
              <button className="btn btn-sm" onClick={() => control("cancel")}>Cancel</button>
              <button className="btn btn-sm" onClick={() => control("resume")}>Resume</button>
              <button className="btn btn-sm" onClick={() => control("retry")}>Retry</button>
            </div>}
            <h4>Metrics</h4><div className="runtime-metrics">{metricEntries(metrics).map(([key, value]) => <div key={key}><small>{key}</small><strong>{String(value)}</strong></div>)}</div>
            {approvals.length > 0 && <><h4>Approvals</h4>{approvals.map((approval) => <div className="runtime-approval" key={approval.approval_id}><span>{String(approval.request.prompt || approval.node_id)}</span><div><button className="btn btn-sm btn-primary" onClick={() => decideRuntimeApproval(approval.approval_id, true, workdir).then(refresh)}>Approve</button><button className="btn btn-sm" onClick={() => decideRuntimeApproval(approval.approval_id, false, workdir).then(refresh)}>Reject</button></div></div>)}</>}
            <h4>Timeline</h4><div className="runtime-timeline">{events.map((event) => <div key={event.event_id}><time>{new Date(event.timestamp).toLocaleTimeString()}</time><code>{event.event_type}</code><span>{event.step_id || "run"}</span></div>)}</div>
            <h4>Artifacts</h4><div className="runtime-artifacts">{artifacts.map((artifact) => <details key={artifact.artifact_id}><summary>{artifact.name || artifact.artifact_type}</summary><pre>{JSON.stringify(artifact.content, null, 2)}</pre></details>)}</div>
          </section>
        </div>
      </main>
    </div>
  );
}
