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
  const [codePaths, setCodePaths] = useState<string[]>([]);
  const [addingCodePath, setAddingCodePath] = useState(false);
  const [codePathBrowsePath, setCodePathBrowsePath] = useState("");
  const [codePathEntries, setCodePathEntries] = useState<DirectoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDirectory(path?: string) {
    setLoading(true);
    setError("");
    try {
      const data = await listDirectories(path);
      setCurrentPath(data.path);
      setEntries(data.entries);
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

  async function loadCodePathDirectory(path?: string) {
    try {
      const data = await listDirectories(path);
      setCodePathBrowsePath(data.path);
      setCodePathEntries(data.entries);
    } catch {
      /* ignore */
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

  function startAddCodePath() {
    setAddingCodePath(true);
    setCodePathBrowsePath(currentPath);
    loadCodePathDirectory(currentPath);
  }

  function addCodePath() {
    if (codePathBrowsePath && !codePaths.includes(codePathBrowsePath)) {
      setCodePaths([...codePaths, codePathBrowsePath]);
    }
    setAddingCodePath(false);
  }

  function removeCodePath(index: number) {
    setCodePaths(codePaths.filter((_, i) => i !== index));
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
        description.trim(),
        codePaths
      );
      onComplete(project);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  }

  const dirs = entries.filter((e) => e.is_dir);
  const codePathDirs = codePathEntries.filter((e) => e.is_dir);

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

      <h4>Select working directory</h4>

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

      {/* Code Paths */}
      <h4>Code Paths (optional)</h4>
      <p className="wizard-hint">
        Additional directories the agent can read and write.
      </p>

      {codePaths.length > 0 && (
        <div className="code-paths-list">
          {codePaths.map((cp, i) => (
            <div key={i} className="code-path-item">
              <code>{cp}</code>
              <button
                className="btn-icon"
                onClick={() => removeCodePath(i)}
                title="Remove"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

      {addingCodePath ? (
        <div className="code-path-browser">
          <div className="wizard-path">
            <code>{codePathBrowsePath}</code>
          </div>
          <div className="wizard-entries" style={{ maxHeight: "200px" }}>
            <button
              className="wizard-entry"
              onClick={() => {
                const parent =
                  codePathBrowsePath.split("/").slice(0, -1).join("/") || "/";
                loadCodePathDirectory(parent);
              }}
            >
              ../ (parent)
            </button>
            {codePathDirs.map((entry) => (
              <button
                key={entry.name}
                className="wizard-entry"
                onClick={() => {
                  const next = codePathBrowsePath
                    ? `${codePathBrowsePath}/${entry.name}`
                    : entry.name;
                  loadCodePathDirectory(next);
                }}
              >
                {entry.name}/
              </button>
            ))}
          </div>
          <div className="code-path-actions">
            <button className="btn btn-primary btn-sm" onClick={addCodePath}>
              Add This Path
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setAddingCodePath(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button className="btn btn-sm" onClick={startAddCodePath}>
          + Add Code Path
        </button>
      )}

      <div style={{ marginTop: "16px" }}>
        <button
          className="btn btn-primary"
          onClick={handleCreate}
          disabled={loading || !currentPath || !projectName.trim()}
        >
          {loading ? "Creating..." : "Create Project"}
        </button>
      </div>
    </div>
  );
}
