import type {
  DirectoryListResponse,
  HealthResponse,
  Project,
  SessionDetail,
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

// ── Sessions ───────────────────────────────────────────────────────────────

/** GET /sessions/:id */
export function getSession(sessionId: string): Promise<SessionDetail> {
  return request(`/sessions/${sessionId}`);
}

// ── Skills ─────────────────────────────────────────────────────────────────

export interface SkillInfo {
  name: string;
  description: string;
  enabled: boolean;
  source: string;
}

/** GET /skills */
export function listSkills(): Promise<{ skills: SkillInfo[] }> {
  return request("/skills");
}

/** POST /skills/:name/enable */
export function enableSkill(name: string): Promise<{ name: string; enabled: boolean }> {
  return request(`/skills/${name}/enable`, { method: "POST" });
}

/** POST /skills/:name/disable */
export function disableSkill(name: string): Promise<{ name: string; enabled: boolean }> {
  return request(`/skills/${name}/disable`, { method: "POST" });
}

// ── Config ─────────────────────────────────────────────────────────────────

export interface ConfigStatus {
  is_ready: boolean;
  missing_fields: string[];
}

/** GET /config/status */
export function getConfigStatus(): Promise<ConfigStatus> {
  return request("/config/status");
}

/** GET /config */
export function getConfig(): Promise<Record<string, unknown>> {
  return request("/config");
}

/** PUT /config */
export function updateConfig(data: {
  model?: string;
  model_base_url?: string;
  model_api_key?: string;
  enable_thinking?: boolean;
  thinking_budget?: number;
}): Promise<{ status: string }> {
  return request("/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── WebSocket Chat ──────────────────────────────────────────────────────────

export type ChatSocketStatus = "connecting" | "connected" | "disconnected";

export interface ChatSocket {
  send: (msg: Record<string, unknown>) => void;
  close: () => void;
  onEvent: ((event: WSEvent) => void) | null;
  onStatus: ((status: ChatSocketStatus) => void) | null;
}

/**
 * Open a WebSocket to /ws/chat/:projectId with auto-reconnect.
 *
 * Usage:
 *   const ws = connectChat("abc123");
 *   ws.onEvent = (e) => console.log(e);
 *   ws.onStatus = (s) => console.log("ws:", s);
 *   ws.send({ type: "message", content: "hello" });
 *   ws.close();
 */
export function connectChat(projectId: string): ChatSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws/chat/${projectId}`;

  let ws: WebSocket;
  let closed = false;
  let reconnectTimer: ReturnType<typeof setTimeout>;
  let retryDelay = 2000;
  const MAX_RETRY_DELAY = 60000;

  const handle: ChatSocket = {
    send(msg) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
      }
    },
    close() {
      closed = true;
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    },
    onEvent: null,
    onStatus: null,
  };

  function connect() {
    handle.onStatus?.("connecting");
    ws = new WebSocket(url);

    ws.onopen = () => {
      handle.onStatus?.("connected");
      retryDelay = 2000; // Reset on successful connection
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WSEvent;
        handle.onEvent?.(event);
      } catch {
        /* ignore non-JSON */
      }
    };

    ws.onclose = () => {
      if (!closed) {
        handle.onStatus?.("disconnected");
        reconnectTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY);
      }
    };

    ws.onerror = () => {
      /* onclose fires after onerror, reconnect handled there */
    };
  }

  connect();
  return handle;
}
