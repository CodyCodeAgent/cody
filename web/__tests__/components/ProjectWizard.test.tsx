import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectWizard from "../../src/components/ProjectWizard";

const mockListDirectories = vi.fn();
const mockInitProject = vi.fn();

vi.mock("../../src/api/client", () => ({
  listDirectories: (...args: unknown[]) => mockListDirectories(...args),
  initProject: (...args: unknown[]) => mockInitProject(...args),
}));

beforeEach(() => {
  mockListDirectories.mockReset();
  mockInitProject.mockReset();
  mockListDirectories.mockResolvedValue({
    path: "/home/user",
    entries: [
      { name: "projects", is_dir: true },
      { name: "documents", is_dir: true },
      { name: "file.txt", is_dir: false },
    ],
  });
});

describe("ProjectWizard", () => {
  it("loads and displays directories on mount", async () => {
    render(<ProjectWizard onComplete={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("projects/")).toBeInTheDocument();
      expect(screen.getByText("documents/")).toBeInTheDocument();
    });
    // Files (non-directories) should not appear
    expect(screen.queryByText("file.txt")).not.toBeInTheDocument();
  });

  it("shows current path", async () => {
    render(<ProjectWizard onComplete={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("/home/user")).toBeInTheDocument();
    });
  });

  it("navigates into subdirectory on click", async () => {
    mockListDirectories
      .mockResolvedValueOnce({
        path: "/home/user",
        entries: [{ name: "projects", is_dir: true }],
      })
      .mockResolvedValueOnce({
        path: "/home/user/projects",
        entries: [{ name: "cody", is_dir: true }],
      });

    render(<ProjectWizard onComplete={vi.fn()} />);
    await waitFor(() => screen.getByText("projects/"));
    await userEvent.click(screen.getByText("projects/"));
    await waitFor(() => {
      expect(screen.getByText("/home/user/projects")).toBeInTheDocument();
      expect(screen.getByText("cody/")).toBeInTheDocument();
    });
  });

  it("calls onComplete after selecting directory", async () => {
    mockInitProject.mockResolvedValue({
      status: "success",
      workdir: "/home/user",
    });
    const onComplete = vi.fn();

    render(<ProjectWizard onComplete={onComplete} />);
    await waitFor(() => screen.getByText("Use this directory"));
    await userEvent.click(screen.getByText("Use this directory"));

    await waitFor(() => {
      expect(mockInitProject).toHaveBeenCalledWith("/home/user");
      expect(onComplete).toHaveBeenCalledWith("/home/user");
    });
  });

  it("shows error when init fails", async () => {
    mockInitProject.mockRejectedValue(new Error("Permission denied"));
    render(<ProjectWizard onComplete={vi.fn()} />);
    await waitFor(() => screen.getByText("Use this directory"));
    await userEvent.click(screen.getByText("Use this directory"));
    await waitFor(() => {
      expect(screen.getByText("Permission denied")).toBeInTheDocument();
    });
  });
});
