import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MessageBubble from "../../src/components/MessageBubble";

describe("MessageBubble", () => {
  it("renders user message with 'You' label", () => {
    render(
      <MessageBubble
        message={{ role: "user", content: "Hello", timestamp: "" }}
      />
    );
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders assistant message with 'Cody' label", () => {
    render(
      <MessageBubble
        message={{ role: "assistant", content: "Hi there!", timestamp: "" }}
      />
    );
    expect(screen.getByText("Cody")).toBeInTheDocument();
    expect(screen.getByText("Hi there!")).toBeInTheDocument();
  });

  it("applies user CSS class for user messages", () => {
    const { container } = render(
      <MessageBubble
        message={{ role: "user", content: "test", timestamp: "" }}
      />
    );
    expect(container.querySelector(".message-user")).toBeInTheDocument();
  });

  it("applies assistant CSS class for assistant messages", () => {
    const { container } = render(
      <MessageBubble
        message={{ role: "assistant", content: "test", timestamp: "" }}
      />
    );
    expect(container.querySelector(".message-assistant")).toBeInTheDocument();
  });
});
