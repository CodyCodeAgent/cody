import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ChatPage from "../../src/pages/ChatPage";

vi.mock("../../src/api/client", () => ({
  getSession: vi.fn().mockResolvedValue({
    id: "s1",
    title: "Test session",
    model: "",
    workdir: "/tmp",
    message_count: 1,
    created_at: "",
    updated_at: "",
    messages: [{ role: "user", content: "Hello Cody", timestamp: "" }],
  }),
  listSessions: vi.fn().mockResolvedValue([]),
  deleteSession: vi.fn().mockResolvedValue({ status: "deleted" }),
  connectChat: () => ({
    send: vi.fn(),
    close: vi.fn(),
    onEvent: null,
  }),
}));

describe("ChatPage", () => {
  it("loads session and renders messages", async () => {
    render(
      <MemoryRouter initialEntries={["/chat/s1"]}>
        <Routes>
          <Route path="/chat/:sessionId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    );
    // First shows loading
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    // Then shows messages
    await waitFor(() => {
      expect(screen.getByText("Hello Cody")).toBeInTheDocument();
    });
  });

  it("renders sidebar", async () => {
    render(
      <MemoryRouter initialEntries={["/chat/s1"]}>
        <Routes>
          <Route path="/chat/:sessionId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Sessions")).toBeInTheDocument();
    });
  });
});
