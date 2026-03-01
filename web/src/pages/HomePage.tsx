import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createSession, listSessions } from "../api/client";
import type { Session } from "../types";
import ProjectWizard from "../components/ProjectWizard";

export default function HomePage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [showWizard, setShowWizard] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    listSessions().then(setSessions).catch(console.error);
  }, []);

  async function handleWizardComplete(workdir: string) {
    const session = await createSession("New chat", workdir);
    navigate(`/chat/${session.id}`);
  }

  return (
    <div className="home-page">
      <header className="home-header">
        <h1>Cody</h1>
        <p>AI Coding Assistant</p>
      </header>

      {showWizard ? (
        <ProjectWizard onComplete={handleWizardComplete} />
      ) : (
        <div className="home-actions">
          <button
            className="btn btn-primary btn-lg"
            onClick={() => setShowWizard(true)}
          >
            New Chat
          </button>
        </div>
      )}

      {sessions.length > 0 && !showWizard && (
        <section className="home-sessions">
          <h2>Recent Sessions</h2>
          <ul className="session-list">
            {sessions.map((s) => (
              <li key={s.id} className="session-item">
                <button
                  className="session-link"
                  onClick={() => navigate(`/chat/${s.id}`)}
                >
                  <span className="session-title">{s.title}</span>
                  <span className="session-meta">
                    {s.message_count} messages · {s.workdir}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
