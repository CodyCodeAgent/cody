import type {
  DirectoryListResponse,
  HealthResponse,
  Project,
  WSEvent,
} from "../types";

const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const msg = body?.detail ?? body?.error?.message ?? resp.statusText;
    throw new Error(msg);
  }
  return resp.json() as Promise<T>;
}

// ── Health ──────────────────────────────────────────────────────────────────

/** GET /api/health */
export function healthCheck(): Promise<HealthResponse> {
  return request("/api/health");
}

// ── Directories ─────────────────────────────────────────────────────────────

/** GET /api/directories */
export function listDirectories(
  path?: string
): Promise<DirectoryListResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return request(`/api/directories${params}`);
}

// ── Projects ────────────────────────────────────────────────────────────────

/** GET /api/projects */
export function listProjects(): Promise<Project[]> {
  return request("/api/projects");
}

/** POST /api/projects */
export function createProject(
  name: string,
  workdir: string,
  description?: string
): Promise<Project> {
  return request("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, workdir, description: description ?? "" }),
  });
}

/** GET /api/projects/:id */
export function getProject(id: string): Promise<Project> {
  return request(`/api/projects/${id}`);
}

/** PUT /api/projects/:id */
export function updateProject(
  id: string,
  data: { name?: string; description?: string }
): Promise<Project> {
  return request(`/api/projects/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/** DELETE /api/projects/:id */
export function deleteProject(id: string): Promise<{ status: string }> {
  return request(`/api/projects/${id}`, { method: "DELETE" });
}

// ── WebSocket Chat ──────────────────────────────────────────────────────────

export interface ChatSocket {
  send: (msg: Record<string, unknown>) => void;
  close: () => void;
  onEvent: ((event: WSEvent) => void) | null;
}

/**
 * Open a WebSocket to /ws/chat/:projectId.
 *
 * Usage:
 *   const ws = connectChat("abc123");
 *   ws.onEvent = (e) => console.log(e);
 *   ws.send({ type: "message", content: "hello" });
 *   ws.close();
 */
export function connectChat(projectId: string): ChatSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws/chat/${projectId}`;
  const ws = new WebSocket(url);

  const handle: ChatSocket = {
    send(msg) {
      ws.send(JSON.stringify(msg));
    },
    close() {
      ws.close();
    },
    onEvent: null,
  };

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data) as WSEvent;
      handle.onEvent?.(event);
    } catch {
      /* ignore non-JSON */
    }
  };

  return handle;
}
