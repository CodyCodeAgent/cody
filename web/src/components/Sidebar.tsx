import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, deleteProject } from "../api/client";
import type { Project } from "../types";

export default function Sidebar({
  currentProjectId,
}: {
  currentProjectId?: string;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    listProjects().then(setProjects).catch(console.error);
  }, [currentProjectId]);

  async function handleDelete(id: string) {
    await deleteProject(id);
    setProjects((prev) => prev.filter((p) => p.id !== id));
    if (id === currentProjectId) {
      navigate("/");
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>Projects</h2>
        <button className="btn btn-sm" onClick={() => navigate("/")}>
          + New
        </button>
      </div>
      <ul className="session-list">
        {projects.map((p) => (
          <li
            key={p.id}
            className={`session-item ${p.id === currentProjectId ? "active" : ""}`}
          >
            <button
              className="session-link"
              onClick={() => navigate(`/chat/${p.id}`)}
            >
              <span className="session-title">{p.name}</span>
              <span className="session-meta">{p.workdir}</span>
            </button>
            <button
              className="btn-icon delete-btn"
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(p.id);
              }}
              aria-label={`Delete project ${p.name}`}
            >
              ×
            </button>
          </li>
        ))}
        {projects.length === 0 && (
          <li className="session-empty">No projects yet</li>
        )}
      </ul>
    </aside>
  );
}
