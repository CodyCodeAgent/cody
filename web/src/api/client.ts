import type {
  DirectoryListResponse,
  HealthResponse,
  ProjectInitResponse,
  Session,
  SessionDetail,
  WSEvent,
} from "../types";

const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const msg = body?.error?.message ?? resp.statusText;
    throw new Error(msg);
  }
  return resp.json() as Promise<T>;
}

/** GET /health */
export function healthCheck(): Promise<HealthResponse> {
  return request("/health");
}

/** GET /api/directories */
export function listDirectories(
  path?: string
): Promise<DirectoryListResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return request(`/api/directories${params}`);
}

/** POST /api/projects/init */
export function initProject(workdir: string): Promise<ProjectInitResponse> {
  return request("/api/projects/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workdir }),
  });
}

/** GET /sessions */
export async function listSessions(): Promise<Session[]> {
  const data = await request<{ sessions: Session[] }>("/sessions");
  return data.sessions;
}

/** POST /sessions */
export function createSession(
  title: string,
  workdir: string
): Promise<Session> {
  const params = new URLSearchParams({ title, workdir });
  return request(`/sessions?${params}`, { method: "POST" });
}

/** GET /sessions/:id */
export function getSession(id: string): Promise<SessionDetail> {
  return request(`/sessions/${id}`);
}

/** DELETE /sessions/:id */
export function deleteSession(id: string): Promise<{ status: string }> {
  return request(`/sessions/${id}`, { method: "DELETE" });
}

/**
 * Open a WebSocket to /ws and return helpers.
 *
 * Usage:
 *   const ws = connectChat();
 *   ws.onEvent = (e) => console.log(e);
 *   ws.send({ type: "run", prompt: "hello", workdir: "/tmp" });
 *   ws.close();
 */
export interface ChatSocket {
  send: (msg: Record<string, unknown>) => void;
  close: () => void;
  onEvent: ((event: WSEvent) => void) | null;
}

export function connectChat(sessionId?: string): ChatSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws`;
  const ws = new WebSocket(url);

  const handle: ChatSocket = {
    send(msg) {
      if (sessionId) {
        msg.session_id = sessionId;
      }
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
