import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ChatWindow from "../../src/components/ChatWindow";

// Mock connectChat
vi.mock("../../src/api/client", () => ({
  connectChat: () => ({
    send: vi.fn(),
    close: vi.fn(),
    onEvent: null,
  }),
}));

describe("ChatWindow", () => {
  it("renders initial messages", () => {
    render(
      <ChatWindow
        sessionId="s1"
        workdir="/tmp"
        initialMessages={[
          { role: "user", content: "Hello", timestamp: "" },
          { role: "assistant", content: "Hi there", timestamp: "" },
        ]}
      />
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
  });

  it("renders input field and send button", () => {
    render(
      <ChatWindow sessionId="s1" workdir="/tmp" initialMessages={[]} />
    );
    expect(screen.getByPlaceholderText("Ask Cody...")).toBeInTheDocument();
    expect(screen.getByText("Send")).toBeInTheDocument();
  });

  it("disables send button when input is empty", () => {
    render(
      <ChatWindow sessionId="s1" workdir="/tmp" initialMessages={[]} />
    );
    expect(screen.getByText("Send")).toBeDisabled();
  });
});
