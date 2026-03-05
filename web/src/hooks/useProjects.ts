import { useCallback, useEffect, useState } from "react";
import { listProjects, deleteProject } from "../api/client";
import type { Project } from "../types";

/** Module-level cache for project list shared across components. */
let cached: Project[] | null = null;
const listeners = new Set<() => void>();

function notify() {
  for (const fn of listeners) fn();
}

/**
 * Shared hook for project list.
 * All consumers see the same data and stay in sync.
 */
export function useProjects() {
  const [projects, setProjects] = useState<Project[]>(cached ?? []);

  useEffect(() => {
    const listener = () => setProjects(cached ?? []);
    listeners.add(listener);
    if (!cached) refresh();
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await listProjects();
      cached = data;
      notify();
    } catch (e) {
      console.error("Failed to load projects:", e);
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    await deleteProject(id);
    cached = (cached ?? []).filter((p) => p.id !== id);
    notify();
  }, []);

  return { projects, refresh, remove };
}
