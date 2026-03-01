import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listSessions, deleteSession } from "../api/client";
import type { Session } from "../types";

export default function Sidebar({
  currentSessionId,
}: {
  currentSessionId?: string;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    listSessions().then(setSessions).catch(console.error);
  }, [currentSessionId]);

  async function handleDelete(id: string) {
    await deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (id === currentSessionId) {
      navigate("/");
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>Sessions</h2>
        <button className="btn btn-sm" onClick={() => navigate("/")}>
          + New
        </button>
      </div>
      <ul className="session-list">
        {sessions.map((s) => (
          <li
            key={s.id}
            className={`session-item ${s.id === currentSessionId ? "active" : ""}`}
          >
            <button
              className="session-link"
              onClick={() => navigate(`/chat/${s.id}`)}
            >
              <span className="session-title">{s.title}</span>
              <span className="session-meta">
                {s.message_count} messages
              </span>
            </button>
            <button
              className="btn-icon delete-btn"
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(s.id);
              }}
              aria-label={`Delete session ${s.title}`}
            >
              ×
            </button>
          </li>
        ))}
        {sessions.length === 0 && (
          <li className="session-empty">No sessions yet</li>
        )}
      </ul>
    </aside>
  );
}
