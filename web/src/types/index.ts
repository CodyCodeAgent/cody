/** Matches backend ProjectResponse */
export interface Project {
  id: string;
  name: string;
  description: string;
  workdir: string;
  session_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Matches backend DirectoryEntry */
export interface DirectoryEntry {
  name: string;
  is_dir: boolean;
}

/** Matches backend DirectoryListResponse */
export interface DirectoryListResponse {
  path: string;
  entries: DirectoryEntry[];
}

/** Matches backend WebHealthResponse */
export interface HealthResponse {
  status: string;
  version: string;
  core_server: string;
  core_version: string | null;
}

/** A single chat message */
export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

/** WebSocket event from server */
export interface WSEvent {
  type:
    | "start"
    | "thinking"
    | "text_delta"
    | "tool_call"
    | "tool_result"
    | "done"
    | "error"
    | "cancelled"
    | "pong";
  content?: string;
  session_id?: string;
  message?: string;
  [key: string]: unknown;
}
