import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useProjects } from "../hooks/useProjects";

export default function Sidebar({
  currentProjectId,
}: {
  currentProjectId?: string;
}) {
  const { projects, refresh, remove } = useProjects();
  const navigate = useNavigate();

  useEffect(() => {
    refresh();
  }, [currentProjectId, refresh]);

  async function handleDelete(id: string) {
    if (!window.confirm("Are you sure you want to delete this project?")) return;
    try {
      await remove(id);
      if (id === currentProjectId) {
        navigate("/");
      }
    } catch (e) {
      console.error("Delete failed:", e);
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
              onClick={() => navigate(`/project/${p.id}`)}
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
      <div className="sidebar-footer">
        <button className="sidebar-nav-btn" onClick={() => navigate("/skills")}>
          Skills
        </button>
        <button className="sidebar-nav-btn" onClick={() => navigate("/settings")}>
          Settings
        </button>
      </div>
    </aside>
  );
}
