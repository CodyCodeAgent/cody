import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Sidebar from "../../src/components/Sidebar";

// Mock navigation
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock API
vi.mock("../../src/api/client", () => ({
  listProjects: vi.fn().mockResolvedValue([
    {
      id: "p1",
      name: "Project Alpha",
      description: "",
      workdir: "/tmp/alpha",
      session_id: null,
      created_at: "",
      updated_at: "",
    },
    {
      id: "p2",
      name: "Project Beta",
      description: "",
      workdir: "/tmp/beta",
      session_id: null,
      created_at: "",
      updated_at: "",
    },
  ]),
  deleteProject: vi.fn().mockResolvedValue({ status: "deleted" }),
}));

beforeEach(() => {
  mockNavigate.mockReset();
});

describe("Sidebar", () => {
  it("renders project list", async () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Project Alpha")).toBeInTheDocument();
      expect(screen.getByText("Project Beta")).toBeInTheDocument();
    });
  });

  it("navigates to project on click", async () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("Project Alpha"));
    await userEvent.click(screen.getByText("Project Alpha"));
    expect(mockNavigate).toHaveBeenCalledWith("/chat/p1");
  });

  it("navigates to home on '+ New' click", async () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("+ New"));
    await userEvent.click(screen.getByText("+ New"));
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });

  it("highlights current project", async () => {
    const { container } = render(
      <MemoryRouter>
        <Sidebar currentProjectId="p1" />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("Project Alpha"));
    const active = container.querySelector(".session-item.active");
    expect(active).toBeInTheDocument();
  });
});
