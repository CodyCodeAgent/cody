import { useEffect, useState } from "react";
import { listDirectories, initProject } from "../api/client";
import type { DirectoryEntry } from "../types";

interface Props {
  onComplete: (workdir: string) => void;
}

export default function ProjectWizard({ onComplete }: Props) {
  const [currentPath, setCurrentPath] = useState("");
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDirectory(path?: string) {
    setLoading(true);
    setError("");
    try {
      const data = await listDirectories(path);
      setCurrentPath(data.path);
      setEntries(data.entries);
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
    loadDirectory(next);
  }

  function navigateUp() {
    const parent = currentPath.split("/").slice(0, -1).join("/") || "/";
    loadDirectory(parent);
  }

  async function handleSelect() {
    setLoading(true);
    setError("");
    try {
      await initProject(currentPath);
      onComplete(currentPath);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to initialize project");
    } finally {
      setLoading(false);
    }
  }

  const dirs = entries.filter((e) => e.is_dir);

  return (
    <div className="wizard">
      <h3>Select project directory</h3>

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
        onClick={handleSelect}
        disabled={loading || !currentPath}
      >
        {loading ? "Initializing..." : "Use this directory"}
      </button>
    </div>
  );
}
