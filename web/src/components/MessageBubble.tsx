import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";

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
      if (val.includes("/")) {
        const parts = val.split("/").filter(Boolean);
        const short = parts.length > 2 ? "…/" + parts.slice(-2).join("/") : val;
        return short.length > 60 ? "…" + short.slice(-57) : short;
      }
      return val.length > 60 ? val.slice(0, 57) + "…" : val;
    }
  } catch {
    /* not JSON */
  }
  if (!args || args === "{}") return "";
  return args.length > 60 ? args.slice(0, 57) + "…" : args;
}

export default function MessageBubble({ message }: { message: Message }) {
  if (message.role === "system") {
    return (
      <div className="message message-system">
        <div className="system-content">{message.content}</div>
      </div>
    );
  }

  const isUser = message.role === "user";

  return (
    <div className={`message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-role">{isUser ? "You" : "Cody"}</div>

      {/* Thinking block (assistant only) */}
      {!isUser && message.thinking && (
        <details className="thinking-block">
          <summary>Thinking</summary>
          <div className="thinking-content">{message.thinking}</div>
        </details>
      )}

      {/* Tool calls (assistant only, collapsed by default) */}
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="tool-calls">
          {message.toolCalls.map((tc) => (
            <details key={tc.id} className="tool-call-card">
              <summary className="tool-call-header">
                <span className="tool-call-icon">✓</span>
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

      {/* Message content */}
      <div className="message-content">
        {isUser ? (
          message.content
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        )}
      </div>

      {/* Token usage (assistant only) */}
      {!isUser && message.usage && (
        <div className="message-usage">
          {message.usage.total_tokens.toLocaleString()} tokens
        </div>
      )}
    </div>
  );
}
