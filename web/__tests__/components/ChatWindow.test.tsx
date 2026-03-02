import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ChatWindow from "../../src/components/ChatWindow";

// Mock API client
vi.mock("../../src/api/client", () => ({
  connectChat: () => ({
    send: vi.fn(),
    close: vi.fn(),
    onEvent: null,
  }),
  getSession: vi.fn().mockRejectedValue(new Error("no session")),
}));

describe("ChatWindow", () => {
  it("renders project name header", () => {
    render(<ChatWindow projectId="p1" projectName="My Project" />);
    expect(screen.getByText("My Project")).toBeInTheDocument();
  });

  it("renders input field and send button", () => {
    render(<ChatWindow projectId="p1" projectName="Test" />);
    expect(screen.getByPlaceholderText("Ask Cody...")).toBeInTheDocument();
    expect(screen.getByText("Send")).toBeInTheDocument();
  });

  it("disables send button when input is empty", () => {
    render(<ChatWindow projectId="p1" projectName="Test" />);
    expect(screen.getByText("Send")).toBeDisabled();
  });
});
