import { useEffect, useState } from "react";
import { listDirectories, createProject } from "../api/client";
import type { DirectoryEntry, Project } from "../types";

interface Props {
  onComplete: (project: Project) => void;
}

export default function ProjectWizard({ onComplete }: Props) {
  const [currentPath, setCurrentPath] = useState("");
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDirectory(path?: string) {
    setLoading(true);
    setError("");
    try {
      const data = await listDirectories(path);
      setCurrentPath(data.path);
      setEntries(data.entries);
      // Default project name to directory name
      if (!projectName) {
        const dirName = data.path.split("/").pop() || "";
        setProjectName(dirName);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to list directory");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDirectory();
  }, []);

  function navigateTo(name: string) {
    const next = currentPath ? `${currentPath}/${name}` : name;
    setProjectName(name);
    loadDirectory(next);
  }

  function navigateUp() {
    const parent = currentPath.split("/").slice(0, -1).join("/") || "/";
    const parentName = parent.split("/").pop() || "";
    setProjectName(parentName);
    loadDirectory(parent);
  }

  async function handleCreate() {
    if (!projectName.trim()) {
      setError("Project name is required");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const project = await createProject(
        projectName.trim(),
        currentPath,
        description.trim()
      );
      onComplete(project);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  }

  const dirs = entries.filter((e) => e.is_dir);

  return (
    <div className="wizard">
      <h3>Create New Project</h3>

      <div className="wizard-fields">
        <label>
          Project Name
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="My Project"
          />
        </label>
        <label>
          Description (optional)
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A brief description"
          />
        </label>
      </div>

      <h4>Select project directory</h4>

      <div className="wizard-path">
        <code>{currentPath}</code>
      </div>

      {error && <div className="wizard-error">{error}</div>}

      <div className="wizard-entries">
        <button className="wizard-entry" onClick={navigateUp} disabled={loading}>
          ../ (parent)
        </button>
        {dirs.map((entry) => (
          <button
            key={entry.name}
            className="wizard-entry"
            onClick={() => navigateTo(entry.name)}
            disabled={loading}
          >
            {entry.name}/
          </button>
        ))}
        {dirs.length === 0 && !loading && (
          <div className="wizard-empty">No subdirectories</div>
        )}
      </div>

      <button
        className="btn btn-primary"
        onClick={handleCreate}
        disabled={loading || !currentPath || !projectName.trim()}
      >
        {loading ? "Creating..." : "Create Project"}
      </button>
    </div>
  );
}
