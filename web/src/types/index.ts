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

/** Matches backend ProjectInitResponse */
export interface ProjectInitResponse {
  status: string;
  workdir: string;
}

/** Matches backend HealthResponse */
export interface HealthResponse {
  status: string;
  version: string;
}

/** Matches backend SessionResponse */
export interface Session {
  id: string;
  title: string;
  model: string;
  workdir: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

/** Matches backend SessionDetailResponse */
export interface SessionDetail extends Session {
  messages: Message[];
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
  [key: string]: unknown;
}
