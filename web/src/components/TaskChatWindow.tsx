import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { connectTaskChat, getConfigStatus, getSession } from "../api/client";
import type { ChatSocket, ChatSocketStatus } from "../api/client";
import type { ImageAttachment, Message, ToolCallInfo, WSEvent } from "../types";
import { summarizeArgs } from "../utils/summarizeArgs";
import MessageBubble from "./MessageBubble";

interface Props {
  taskId: string;
  taskName: string;
  branchName: string;
  projectName: string;
  projectId: string;
  sessionId?: string | null;
}

interface StreamBuffer {
  content: string;
  thinking: string;
  toolCalls: ToolCallInfo[];
}

export default function TaskChatWindow({
  taskId,
  taskName,
  branchName,
  projectName,
  sessionId,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [wsStatus, setWsStatus] = useState<ChatSocketStatus>("connecting");
  const [configReady, setConfigReady] = useState<boolean | null>(null);
  const [configMissing, setConfigMissing] = useState<string[]>([]);

  const [streamContent, setStreamContent] = useState("");
  const [streamThinking, setStreamThinking] = useState("");
  const [streamToolCalls, setStreamToolCalls] = useState<ToolCallInfo[]>([]);

  const [interactionRequest, setInteractionRequest] = useState<{
    requestId: string;
    prompt: string;
    options?: string[];
  } | null>(null);

  const [pendingImages, setPendingImages] = useState<ImageAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingRef = useRef(false);

  const bufferRef = useRef<StreamBuffer>({
    content: "",
    thinking: "",
    toolCalls: [],
  });
  const rafRef = useRef(0);

  const flushBuffer = useCallback(() => {
    rafRef.current = 0;
    const b = bufferRef.current;
    setStreamContent(b.content);
    setStreamThinking(b.thinking);
    setStreamToolCalls([...b.toolCalls]);
  }, []);

  const scheduleFlush = useCallback(() => {
    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(flushBuffer);
    }
  }, [flushBuffer]);

  const resetBuffer = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }
    bufferRef.current = { content: "", thinking: "", toolCalls: [] };
    setStreamContent("");
    setStreamThinking("");
    setStreamToolCalls([]);
  }, []);

  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, streamContent, streamThinking, streamToolCalls]);

  // Load chat history
  useEffect(() => {
    if (!sessionId) return;
    getSession(sessionId)
      .then((detail) => {
        const history: Message[] = detail.messages
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            timestamp: m.timestamp,
            images: m.images || undefined,
          }));
        setMessages(history);
      })
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    getConfigStatus()
      .then((status) => {
        setConfigReady(status.is_ready);
        setConfigMissing(status.missing_fields);
      })
      .catch(() => setConfigReady(true));
  }, []);

  // Connect task WebSocket
  useEffect(() => {
    const sock = connectTaskChat(taskId);
    socketRef.current = sock;

    sock.onStatus = (status: ChatSocketStatus) => {
      setWsStatus(status);
      if (status === "disconnected" && streamingRef.current) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system" as const,
            content: "Connection lost — response interrupted.",
            timestamp: new Date().toISOString(),
          },
        ]);
        resetBuffer();
        setStreaming(false);
      }
    };

    sock.onEvent = (event: WSEvent) => {
      const buf = bufferRef.current;
      lastEventRef.current = Date.now();

      switch (event.type) {
        case "thinking":
          buf.thinking += event.content ?? "";
          scheduleFlush();
          break;
        case "text_delta":
          buf.content += event.content ?? "";
          scheduleFlush();
          break;
        case "tool_call":
          buf.toolCalls = [
            ...buf.toolCalls,
            {
              id: event.tool_call_id ?? String(Date.now()),
              name: event.tool_name ?? "tool",
              args:
                typeof event.args === "string"
                  ? event.args
                  : JSON.stringify(event.args ?? {}),
              loading: true,
            },
          ];
          scheduleFlush();
          break;
        case "tool_result":
          buf.toolCalls = buf.toolCalls.map((tc) =>
            tc.id === event.tool_call_id
              ? { ...tc, result: event.result ?? "", loading: false }
              : tc
          );
          scheduleFlush();
          break;
        case "compact":
          setMessages((prev) => [
            ...prev,
            {
              role: "system",
              content: `Context compacted: ${event.original_messages ?? 0} → ${event.compacted_messages ?? 0} messages`,
              timestamp: new Date().toISOString(),
            },
          ]);
          break;
        case "interaction_request": {
          const reqId = event.request_id ?? "";
          const prompt = event.prompt ?? event.content ?? "The AI has a question";
          const options = event.options as string[] | undefined;
          setInteractionRequest({ requestId: reqId, prompt, options });
          scheduleFlush();
          break;
        }
        case "done": {
          if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = 0;
          }
          const finalContent = event.output ?? event.content ?? "";
          const finalThinking = event.thinking ?? undefined;
          const finalToolCalls = event.tool_traces?.map((t, i) => ({
            id: String(i),
            name: t.tool_name,
            args:
              typeof t.args === "string"
                ? t.args
                : JSON.stringify(t.args ?? {}),
            result:
              typeof t.result === "string"
                ? t.result
                : JSON.stringify(t.result ?? ""),
            loading: false,
          }));
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: finalContent,
              timestamp: new Date().toISOString(),
              thinking: finalThinking,
              toolCalls: finalToolCalls,
              usage: event.usage ?? undefined,
            },
          ]);
          bufferRef.current = { content: "", thinking: "", toolCalls: [] };
          setStreamContent("");
          setStreamThinking("");
          setStreamToolCalls([]);
          setStreaming(false);
          setInteractionRequest(null);
          break;
        }
        case "config_required":
          setConfigReady(false);
          setConfigMissing(
            (event as unknown as { missing_fields?: string[] })
              .missing_fields ?? []
          );
          resetBuffer();
          setStreaming(false);
          break;
        case "error":
          if (event.message) {
            setMessages((prev) => [
              ...prev,
              {
                role: "system",
                content: `Error: ${event.message}`,
                timestamp: new Date().toISOString(),
              },
            ]);
          }
          resetBuffer();
          setStreaming(false);
          setInteractionRequest(null);
          break;
      }
    };

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      sock.close();
    };
  }, [taskId, scheduleFlush, resetBuffer]);

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (!blob) continue;
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(",")[1];
          setPendingImages((prev) => [
            ...prev,
            { data: base64, media_type: item.type, filename: blob.name },
          ]);
        };
        reader.readAsDataURL(blob);
      }
    }
  }, []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      for (const file of files) {
        if (!file.type.startsWith("image/")) continue;
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(",")[1];
          setPendingImages((prev) => [
            ...prev,
            { data: base64, media_type: file.type, filename: file.name },
          ]);
        };
        reader.readAsDataURL(file);
      }
      e.target.value = "";
    },
    []
  );

  const handleSend = useCallback(() => {
    const text = input.trim();

    // If there's a pending interaction request, submit the response
    if (interactionRequest && text) {
      socketRef.current?.send({
        type: "submit_interaction",
        request_id: interactionRequest.requestId,
        action: "answer",
        content: text,
      });
      setInput("");
      setInteractionRequest(null);
      return;
    }

    if ((!text && pendingImages.length === 0) || streaming) return;

    const userMsg: Message = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
      images: pendingImages.length > 0 ? pendingImages : undefined,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setPendingImages([]);
    setStreaming(true);
    resetBuffer();

    const payload: Record<string, unknown> = {
      type: "message",
      content: text,
    };
    if (pendingImages.length > 0) payload.images = pendingImages;
    socketRef.current?.send(payload);
  }, [input, streaming, pendingImages, resetBuffer, interactionRequest]);

  const hasStreamActivity =
    streaming &&
    (streamThinking || streamToolCalls.length > 0 || streamContent);

  // Elapsed timer
  const [elapsed, setElapsed] = useState(0);
  const lastEventRef = useRef(0);

  useEffect(() => {
    if (!streaming) {
      setElapsed(0);
      return;
    }
    lastEventRef.current = Date.now();
    const t0 = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - t0) / 1000));
      if (Date.now() - lastEventRef.current > 120_000) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system" as const,
            content: "Response timed out (no data for 120s).",
            timestamp: new Date().toISOString(),
          },
        ]);
        resetBuffer();
        setStreaming(false);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [streaming, resetBuffer]);

  const formatElapsed = (s: number) => {
    if (s < 60) return `${s}s`;
    return `${Math.floor(s / 60)}m ${s % 60}s`;
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div className="task-chat-header-info">
          <h3>{taskName}</h3>
          <span className="task-chat-meta">
            {projectName} &middot;{" "}
            <code className="task-branch-badge">{branchName}</code>
          </span>
        </div>
        {wsStatus !== "connected" && (
          <span className={`ws-status ws-status-${wsStatus}`}>
            {wsStatus === "connecting"
              ? "Connecting..."
              : "Disconnected — reconnecting..."}
          </span>
        )}
      </div>
      {configReady === false && (
        <div className="config-banner">
          <div className="config-banner-icon">!</div>
          <div className="config-banner-text">
            <strong>Configuration required</strong>
            <p>
              {configMissing.length > 0
                ? configMissing.join(", ")
                : "Model and API base URL must be configured."}
            </p>
          </div>
          <a className="btn btn-primary btn-sm" href="/settings">
            Go to Settings
          </a>
        </div>
      )}

      <div className="messages">
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {hasStreamActivity && (
          <div className="message message-assistant">
            <div className="message-role">Cody</div>
            {streamThinking && (
              <details className="thinking-block" open>
                <summary>Thinking...</summary>
                <div className="thinking-content">{streamThinking}</div>
              </details>
            )}
            {streamToolCalls.length > 0 && (
              <div className="tool-calls">
                {streamToolCalls.map((tc) => (
                  <details
                    key={tc.id}
                    className={`tool-call-card ${tc.loading ? "tool-loading" : ""}`}
                    open={tc.loading}
                  >
                    <summary className="tool-call-header">
                      <span className="tool-call-icon">
                        {tc.loading ? "\u27F3" : "\u2713"}
                      </span>
                      <span className="tool-call-name">{tc.name}</span>
                      {summarizeArgs(tc.args) && (
                        <span className="tool-call-args">
                          {summarizeArgs(tc.args)}
                        </span>
                      )}
                    </summary>
                    {tc.result && (
                      <pre className="tool-call-result">{tc.result}</pre>
                    )}
                  </details>
                ))}
              </div>
            )}
            {streamContent && (
              <div className="message-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamContent}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {interactionRequest && (
          <div className="interaction-request">
            <div className="interaction-request-icon">?</div>
            <div className="interaction-request-body">
              <div className="interaction-request-prompt">{interactionRequest.prompt}</div>
              {interactionRequest.options && interactionRequest.options.length > 0 && (
                <div className="interaction-request-options">
                  {interactionRequest.options.map((opt, i) => (
                    <button
                      key={i}
                      className="btn btn-sm interaction-option"
                      onClick={() => {
                        socketRef.current?.send({
                          type: "submit_interaction",
                          request_id: interactionRequest.requestId,
                          action: "answer",
                          content: opt,
                        });
                        setInteractionRequest(null);
                      }}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {streaming && !interactionRequest && (
          <div className="stream-status">
            <span className="stream-status-dot" />
            <span className="stream-status-text">
              {!hasStreamActivity
                ? "Thinking..."
                : streamToolCalls.some((tc) => tc.loading)
                  ? `Running ${streamToolCalls.filter((tc) => tc.loading).slice(-1)[0]?.name ?? "tool"}...`
                  : "Generating..."}
            </span>
            <span className="stream-status-time">
              {formatElapsed(elapsed)}
            </span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {pendingImages.length > 0 && (
        <div className="image-preview-bar">
          {pendingImages.map((img, i) => (
            <div key={i} className="image-preview-item">
              <img
                src={`data:${img.media_type};base64,${img.data}`}
                alt={img.filename || "image"}
              />
              <button
                type="button"
                className="image-preview-remove"
                onClick={() =>
                  setPendingImages((prev) => prev.filter((_, j) => j !== i))
                }
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        onPaste={handlePaste}
      >
        <button
          type="button"
          className="btn-icon image-upload-btn"
          onClick={() => fileInputRef.current?.click()}
          title="Attach image"
          disabled={streaming}
        >
          +
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: "none" }}
          onChange={handleFileSelect}
        />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            configReady === false
              ? "Configure model in Settings first..."
              : interactionRequest
                ? "Type your answer..."
                : "Describe what to code..."
          }
          disabled={(streaming && !interactionRequest) || configReady === false}
        />
        <button
          type="submit"
          disabled={
            (streaming && !interactionRequest) ||
            configReady === false ||
            (!input.trim() && pendingImages.length === 0 && !interactionRequest)
          }
        >
          Send
        </button>
      </form>
    </div>
  );
}
