import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import RuntimePage from "../../src/pages/RuntimePage";

vi.mock("../../src/api/client", () => ({
  listProjects: vi.fn().mockResolvedValue([{ id: "p1", name: "Demo", workdir: "/repo" }]),
  listRuntimeRuns: vi.fn().mockResolvedValue({ runs: [{ run_id: "run_123", task: "Fix tests", status: "waiting", updated_at: "", metadata: {} }] }),
  getRuntimeRun: vi.fn().mockResolvedValue({ run: { run_id: "run_123", task: "Fix tests", status: "waiting", updated_at: "", metadata: {} }, steps: [] }),
  getRuntimeTimeline: vi.fn().mockResolvedValue({ events: [{ event_id: "e1", event_type: "run.waiting", timestamp: "2026-01-01T00:00:00Z", payload: {} }] }),
  getRuntimeMetrics: vi.fn().mockResolvedValue({ metrics: { total_tokens: 42, tool_calls: 1 } }),
  listRuntimeArtifacts: vi.fn().mockResolvedValue({ artifacts: [] }),
  listRuntimeApprovals: vi.fn().mockResolvedValue({ approvals: [{ approval_id: "a1", run_id: "run_123", node_id: "tool", status: "pending", request: { prompt: "exec_command" } }] }),
  startRuntimeRun: vi.fn(),
  controlRuntimeRun: vi.fn(),
  decideRuntimeApproval: vi.fn(),
  deleteProject: vi.fn(),
}));

describe("RuntimePage", () => {
  it("shows canonical run state, metrics, approvals and timeline", async () => {
    render(<MemoryRouter><RuntimePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText("Fix tests").length).toBeGreaterThan(0));
    expect(screen.getByText("run.waiting")).toBeInTheDocument();
    expect(screen.getByText("Approve")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });
});
