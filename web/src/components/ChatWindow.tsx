import { useCallback, useEffect, useRef, useState } from "react";
import { connectChat } from "../api/client";
import type { ChatSocket } from "../api/client";
import type { Message, WSEvent } from "../types";
import MessageBubble from "./MessageBubble";

interface Props {
  projectId: string;
  projectName: string;
}

export default function ChatWindow({ projectId, projectName }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState("");
  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, streamContent]);

  // Connect WebSocket
  useEffect(() => {
    const sock = connectChat(projectId);
    socketRef.current = sock;

    sock.onEvent = (event: WSEvent) => {
      switch (event.type) {
        case "text_delta":
          setStreamContent((prev) => prev + (event.content ?? ""));
          break;
        case "done": {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: event.content ?? "",
              timestamp: new Date().toISOString(),
            },
          ]);
          setStreamContent("");
          setStreaming(false);
          break;
        }
        case "error":
          setStreamContent("");
          setStreaming(false);
          break;
      }
    };

    return () => sock.close();
  }, [projectId]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMsg: Message = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    setStreamContent("");

    socketRef.current?.send({
      type: "message",
      content: text,
    });
  }, [input, streaming]);

  return (
    <div className="chat-window">
      <div className="chat-header">
        <h3>{projectName}</h3>
      </div>
      <div className="messages">
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {streaming && streamContent && (
          <div className="message message-assistant">
            <div className="message-role">Cody</div>
            <div className="message-content">{streamContent}</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Cody..."
          disabled={streaming}
        />
        <button type="submit" disabled={streaming || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
