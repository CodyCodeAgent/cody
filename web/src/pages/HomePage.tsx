import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Project } from "../types";
import { useProjects } from "../hooks/useProjects";
import ProjectWizard from "../components/ProjectWizard";

export default function HomePage() {
  const { projects } = useProjects();
  const [showWizard, setShowWizard] = useState(false);
  const navigate = useNavigate();

  function handleProjectCreated(project: Project) {
    navigate(`/chat/${project.id}`);
  }

  return (
    <div className="home-page">
      <header className="home-header">
        <h1>Cody</h1>
        <p>AI Coding Assistant</p>
      </header>

      {showWizard ? (
        <ProjectWizard onComplete={handleProjectCreated} />
      ) : (
        <div className="home-actions">
          <button
            className="btn btn-primary btn-lg"
            onClick={() => setShowWizard(true)}
          >
            New Project
          </button>
        </div>
      )}

      {projects.length > 0 && !showWizard && (
        <section className="home-sessions">
          <h2>Recent Projects</h2>
          <ul className="session-list">
            {projects.map((p) => (
              <li key={p.id} className="session-item">
                <button
                  className="session-link"
                  onClick={() => navigate(`/chat/${p.id}`)}
                >
                  <span className="session-title">{p.name}</span>
                  <span className="session-meta">
                    {p.description ? `${p.description} · ` : ""}
                    {p.workdir}
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
