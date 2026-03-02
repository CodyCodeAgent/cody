import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import HomePage from "../../src/pages/HomePage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../../src/api/client", () => ({
  listProjects: vi.fn().mockResolvedValue([
    {
      id: "p1",
      name: "My Project",
      description: "A test project",
      workdir: "/tmp",
      session_id: null,
      created_at: "",
      updated_at: "",
    },
  ]),
  listDirectories: vi.fn().mockResolvedValue({
    path: "/home/user",
    entries: [{ name: "project", is_dir: true }],
  }),
  createProject: vi.fn().mockResolvedValue({
    id: "new1",
    name: "user",
    workdir: "/home/user",
  }),
}));

describe("HomePage", () => {
  it("renders title and new project button", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    expect(screen.getByText("Cody")).toBeInTheDocument();
    expect(screen.getByText("New Project")).toBeInTheDocument();
  });

  it("shows recent projects", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("My Project")).toBeInTheDocument();
    });
  });

  it("navigates to project on click", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("My Project"));
    await userEvent.click(screen.getByText("My Project"));
    expect(mockNavigate).toHaveBeenCalledWith("/chat/p1");
  });

  it("shows project wizard when New Project is clicked", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    await userEvent.click(screen.getByText("New Project"));
    await waitFor(() => {
      expect(screen.getByText("Create New Project")).toBeInTheDocument();
    });
  });
});
