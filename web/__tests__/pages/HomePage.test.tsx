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
  listSessions: vi.fn().mockResolvedValue([
    {
      id: "s1",
      title: "Old chat",
      message_count: 5,
      workdir: "/tmp",
      model: "",
      created_at: "",
      updated_at: "",
    },
  ]),
  createSession: vi.fn().mockResolvedValue({ id: "new1" }),
  listDirectories: vi.fn().mockResolvedValue({
    path: "/home/user",
    entries: [{ name: "project", is_dir: true }],
  }),
  initProject: vi.fn().mockResolvedValue({ status: "success", workdir: "/home/user" }),
}));

describe("HomePage", () => {
  it("renders title and new chat button", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    expect(screen.getByText("Cody")).toBeInTheDocument();
    expect(screen.getByText("New Chat")).toBeInTheDocument();
  });

  it("shows recent sessions", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Old chat")).toBeInTheDocument();
    });
  });

  it("navigates to session on click", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("Old chat"));
    await userEvent.click(screen.getByText("Old chat"));
    expect(mockNavigate).toHaveBeenCalledWith("/chat/s1");
  });

  it("shows project wizard when New Chat is clicked", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    await userEvent.click(screen.getByText("New Chat"));
    await waitFor(() => {
      expect(screen.getByText("Select project directory")).toBeInTheDocument();
    });
  });
});
