import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getSession } from "../api/client";
import type { Message } from "../types";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [workdir, setWorkdir] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    getSession(sessionId)
      .then((detail) => {
        setMessages(detail.messages);
        setWorkdir(detail.workdir);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (!sessionId) {
    return <div>No session selected</div>;
  }

  return (
    <div className="chat-page">
      <Sidebar currentSessionId={sessionId} />
      <main className="chat-main">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : (
          <ChatWindow
            sessionId={sessionId}
            workdir={workdir}
            initialMessages={messages}
          />
        )}
      </main>
    </div>
  );
}
