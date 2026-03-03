import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { connectChat, getSession } from "../api/client";
import type { ChatSocket, ChatSocketStatus } from "../api/client";
import type { ImageAttachment, Message, ToolCallInfo, WSEvent } from "../types";
import MessageBubble from "./MessageBubble";

/** Extract a short summary from tool args JSON for display in collapsed header. */
function summarizeArgs(args: unknown): string {
  if (typeof args !== "string") {
    if (args && typeof args === "object") return summarizeArgs(JSON.stringify(args));
    return "";
  }
  try {
    const obj = JSON.parse(args);
    const val =
      obj.file_path ?? obj.path ?? obj.command ?? obj.query ?? obj.pattern ?? obj.url;
    if (typeof val === "string") {
      // For paths, show last 2 segments to keep it short
      if (val.includes("/")) {
        const parts = val.split("/").filter(Boolean);
        const short = parts.length > 2 ? "…/" + parts.slice(-2).join("/") : val;
        return short.length > 60 ? "…" + short.slice(-57) : short;
      }
      return val.length > 60 ? val.slice(0, 57) + "…" : val;
    }
  } catch {
    /* not JSON, fall through */
  }
  if (!args || args === "{}") return "";
  return args.length > 60 ? args.slice(0, 57) + "…" : args;
}

interface Props {
  projectId: string;
  projectName: string;
  sessionId?: string | null;
}

/** Mutable accumulator for streaming data — lives in a ref to skip per-event re-renders. */
interface StreamBuffer {
  content: string;
  thinking: string;
  toolCalls: ToolCallInfo[];
}

export default function ChatWindow({ projectId, projectName, sessionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [wsStatus, setWsStatus] = useState<ChatSocketStatus>("connecting");

  // Display state (flushed from buffer at screen refresh rate)
  const [streamContent, setStreamContent] = useState("");
  const [streamThinking, setStreamThinking] = useState("");
  const [streamToolCalls, setStreamToolCalls] = useState<ToolCallInfo[]>([]);

  // Settings panel state
  const [showSettings, setShowSettings] = useState(false);
  const [modelOverride, setModelOverride] = useState("");
  const [baseUrlOverride, setBaseUrlOverride] = useState("");
  const [apiKeyOverride, setApiKeyOverride] = useState("");
  const [enableThinking, setEnableThinking] = useState(false);
  const [thinkingBudget, setThinkingBudget] = useState("");

  // Image upload state
  const [pendingImages, setPendingImages] = useState<ImageAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingRef = useRef(false);

  // ── RAF batching: accumulate events in ref, flush to state at ~60fps ──
  const bufferRef = useRef<StreamBuffer>({ content: "", thinking: "", toolCalls: [] });
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

  // Keep streamingRef in sync so WebSocket callbacks see the latest value
  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, streamContent, streamThinking, streamToolCalls]);

  // Load chat history from session API
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
      .catch(() => {
        /* session may not exist yet */
      });
  }, [sessionId]);

  // Connect WebSocket
  useEffect(() => {
    const sock = connectChat(projectId);
    socketRef.current = sock;

    sock.onStatus = (status: ChatSocketStatus) => {
      setWsStatus(status);
      // If WebSocket disconnects while streaming, the response is lost — reset
      if (status === "disconnected" && streamingRef.current) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system" as const,
            content: "Connection lost — response interrupted. Please try again.",
            timestamp: new Date().toISOString(),
          },
        ]);
        resetBuffer();
        setStreaming(false);
      }
    };

    sock.onEvent = (event: WSEvent) => {
      const buf = bufferRef.current;
      // Refresh idle timer on every event
      lastEventRef.current = Date.now();

      switch (event.type) {
        case "thinking":
          buf.thinking += (event.content ?? "");
          scheduleFlush();
          break;

        case "text_delta":
          buf.content += (event.content ?? "");
          scheduleFlush();
          break;

        case "tool_call":
          buf.toolCalls = [
            ...buf.toolCalls,
            {
              id: event.tool_call_id ?? String(Date.now()),
              name: event.tool_name ?? "tool",
              args: typeof event.args === "string" ? event.args : JSON.stringify(event.args ?? {}),
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
              content: `Context compacted: ${event.original_messages ?? 0} → ${event.compacted_messages ?? 0} messages (saved ~${event.estimated_tokens_saved ?? 0} tokens)`,
              timestamp: new Date().toISOString(),
            },
          ]);
          break;

        case "done": {
          // Cancel any pending RAF — we flush the final state directly
          if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = 0;
          }

          const finalContent = event.output ?? event.content ?? "";
          const finalThinking = event.thinking ?? undefined;
          const finalToolCalls = event.tool_traces?.map((t, i) => ({
            id: String(i),
            name: t.tool_name,
            args: typeof t.args === "string" ? t.args : JSON.stringify(t.args ?? {}),
            result: typeof t.result === "string" ? t.result : JSON.stringify(t.result ?? ""),
            loading: false,
          }));
          const finalUsage = event.usage ?? undefined;

          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: finalContent,
              timestamp: new Date().toISOString(),
              thinking: finalThinking,
              toolCalls: finalToolCalls,
              usage: finalUsage,
            },
          ]);
          bufferRef.current = { content: "", thinking: "", toolCalls: [] };
          setStreamContent("");
          setStreamThinking("");
          setStreamToolCalls([]);
          setStreaming(false);
          break;
        }

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
          break;
      }
    };

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      sock.close();
    };
  }, [projectId, scheduleFlush, resetBuffer]);

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

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
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
  }, []);

  const handleSend = useCallback(() => {
    const text = input.trim();
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
    if (modelOverride) payload.model = modelOverride;
    if (baseUrlOverride) payload.model_base_url = baseUrlOverride;
    if (apiKeyOverride) payload.model_api_key = apiKeyOverride;
    if (enableThinking) payload.enable_thinking = true;
    if (thinkingBudget) payload.thinking_budget = parseInt(thinkingBudget, 10) || undefined;

    socketRef.current?.send(payload);
  }, [input, streaming, pendingImages, modelOverride, baseUrlOverride, apiKeyOverride, enableThinking, thinkingBudget, resetBuffer]);

  const hasStreamActivity = streaming && (streamThinking || streamToolCalls.length > 0 || streamContent);

  // ── Elapsed timer while streaming ──
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
      // Idle timeout: no events for 120s → auto-stop
      if (Date.now() - lastEventRef.current > 120_000) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system" as const,
            content: "Response timed out (no data for 120s). Please try again.",
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
        <h3>{projectName}</h3>
        {wsStatus !== "connected" && (
          <span className={`ws-status ws-status-${wsStatus}`}>
            {wsStatus === "connecting" ? "Connecting..." : "Disconnected — reconnecting..."}
          </span>
        )}
      </div>
      <div className="messages">
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {/* Streaming bubble */}
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
                      <span className="tool-call-icon">{tc.loading ? "⟳" : "✓"}</span>
                      <span className="tool-call-name">{tc.name}</span>
                      {summarizeArgs(tc.args) && (
                        <span className="tool-call-args">{summarizeArgs(tc.args)}</span>
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
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamContent}</ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {/* Streaming status bar */}
        {streaming && (
          <div className="stream-status">
            <span className="stream-status-dot" />
            <span className="stream-status-text">
              {!hasStreamActivity
                ? "Thinking..."
                : streamToolCalls.some((tc) => tc.loading)
                  ? `Running ${streamToolCalls.filter((tc) => tc.loading).slice(-1)[0]?.name ?? "tool"}...`
                  : "Generating..."}
            </span>
            <span className="stream-status-time">{formatElapsed(elapsed)}</span>
            <button
              type="button"
              className="stream-stop-btn"
              onClick={() => {
                resetBuffer();
                setStreaming(false);
                setMessages((prev) => [
                  ...prev,
                  {
                    role: "system" as const,
                    content: "Stopped by user.",
                    timestamp: new Date().toISOString(),
                  },
                ]);
              }}
              title="Stop generating"
            >
              Stop
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="chat-settings">
          <label className="setting-item">
            <span>Model</span>
            <input
              type="text"
              value={modelOverride}
              onChange={(e) => setModelOverride(e.target.value)}
              placeholder="default"
              className="setting-input"
            />
          </label>
          <label className="setting-item">
            <span>Base URL</span>
            <input
              type="text"
              value={baseUrlOverride}
              onChange={(e) => setBaseUrlOverride(e.target.value)}
              placeholder="https://api.openai.com/v1"
              className="setting-input"
            />
          </label>
          <label className="setting-item">
            <span>API Key</span>
            <input
              type="password"
              value={apiKeyOverride}
              onChange={(e) => setApiKeyOverride(e.target.value)}
              placeholder="sk-..."
              className="setting-input"
            />
          </label>
          <label className="setting-item">
            <span>Thinking</span>
            <input
              type="checkbox"
              checked={enableThinking}
              onChange={(e) => setEnableThinking(e.target.checked)}
            />
          </label>
          {enableThinking && (
            <label className="setting-item">
              <span>Budget</span>
              <input
                type="number"
                value={thinkingBudget}
                onChange={(e) => setThinkingBudget(e.target.value)}
                placeholder="10000"
                className="setting-input setting-input-sm"
              />
            </label>
          )}
        </div>
      )}

      {/* Pending image previews */}
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
                onClick={() => setPendingImages((prev) => prev.filter((_, j) => j !== i))}
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
          className="btn-icon settings-toggle"
          onClick={() => setShowSettings((v) => !v)}
          title="Settings"
        >
          {showSettings ? "\u25BC" : "\u25B2"}
        </button>
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
          placeholder="Ask Cody..."
          disabled={streaming}
        />
        <button type="submit" disabled={streaming || (!input.trim() && pendingImages.length === 0)}>
          Send
        </button>
      </form>
    </div>
  );
}
