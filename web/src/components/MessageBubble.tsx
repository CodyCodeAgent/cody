import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";
import { summarizeArgs } from "../utils/summarizeArgs";

export default function MessageBubble({ message }: { message: Message }) {
  if (message.role === "system") {
    const isError = message.content.startsWith("Error:");
    return (
      <div className="message message-system">
        <div className={isError ? "system-content-error" : "system-content"}>
          {message.content}
        </div>
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

      {/* Images (user messages with attachments) */}
      {isUser && message.images && message.images.length > 0 && (
        <div className="message-images">
          {message.images.map((img, i) => (
            <img
              key={i}
              src={`data:${img.media_type};base64,${img.data}`}
              alt={img.filename || `image-${i}`}
              className="message-image"
            />
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
