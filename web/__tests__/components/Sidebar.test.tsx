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
  listSessions: vi.fn().mockResolvedValue([
    {
      id: "s1",
      title: "Session 1",
      message_count: 3,
      workdir: "/tmp",
      model: "",
      created_at: "",
      updated_at: "",
    },
    {
      id: "s2",
      title: "Session 2",
      message_count: 0,
      workdir: "/tmp",
      model: "",
      created_at: "",
      updated_at: "",
    },
  ]),
  deleteSession: vi.fn().mockResolvedValue({ status: "deleted" }),
}));

beforeEach(() => {
  mockNavigate.mockReset();
});

describe("Sidebar", () => {
  it("renders session list", async () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Session 1")).toBeInTheDocument();
      expect(screen.getByText("Session 2")).toBeInTheDocument();
    });
  });

  it("navigates to session on click", async () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("Session 1"));
    await userEvent.click(screen.getByText("Session 1"));
    expect(mockNavigate).toHaveBeenCalledWith("/chat/s1");
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

  it("highlights current session", async () => {
    const { container } = render(
      <MemoryRouter>
        <Sidebar currentSessionId="s1" />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("Session 1"));
    const active = container.querySelector(".session-item.active");
    expect(active).toBeInTheDocument();
  });
});
