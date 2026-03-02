import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ChatPage from "../../src/pages/ChatPage";

vi.mock("../../src/api/client", () => ({
  getProject: vi.fn().mockResolvedValue({
    id: "p1",
    name: "Test Project",
    description: "",
    workdir: "/tmp",
    session_id: "sess1",
    created_at: "",
    updated_at: "",
  }),
  listProjects: vi.fn().mockResolvedValue([]),
  deleteProject: vi.fn().mockResolvedValue({ status: "deleted" }),
  connectChat: () => ({
    send: vi.fn(),
    close: vi.fn(),
    onEvent: null,
  }),
}));

describe("ChatPage", () => {
  it("loads project and renders chat window", async () => {
    render(
      <MemoryRouter initialEntries={["/chat/p1"]}>
        <Routes>
          <Route path="/chat/:projectId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    );
    // First shows loading
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    // Then shows project name in chat header
    await waitFor(() => {
      expect(screen.getByText("Test Project")).toBeInTheDocument();
    });
  });

  it("renders sidebar with Projects header", async () => {
    render(
      <MemoryRouter initialEntries={["/chat/p1"]}>
        <Routes>
          <Route path="/chat/:projectId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Projects")).toBeInTheDocument();
    });
  });
});
