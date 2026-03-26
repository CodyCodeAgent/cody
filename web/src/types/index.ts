/** Matches backend ProjectResponse */
export interface Project {
  id: string;
  name: string;
  description: string;
  workdir: string;
  code_paths: string[];
  session_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Matches backend TaskResponse */
export interface Task {
  id: string;
  project_id: string;
  name: string;
  branch_name: string;
  session_id: string | null;
  status: string;
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

/** An image attached to a user message */
export interface ImageAttachment {
  data: string; // base64-encoded
  media_type: string; // "image/png", "image/jpeg", etc.
  filename?: string;
}

/** Tool call info tracked during streaming */
export interface ToolCallInfo {
  id: string;
  name: string;
  args: string;
  result?: string;
  loading: boolean;
}

/** A single chat message */
export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  thinking?: string;
  toolCalls?: ToolCallInfo[];
  usage?: { total_tokens: number };
  images?: ImageAttachment[];
}

/** WebSocket event from server */
export interface WSEvent {
  type:
    | "start"
    | "thinking"
    | "text_delta"
    | "tool_call"
    | "tool_result"
    | "compact"
    | "done"
    | "error"
    | "cancelled"
    | "retry"
    | "resuming"
    | "pong"
    | "config_required"
    | "interaction_request"
    | "user_input_received";
  content?: string;
  output?: string;
  thinking?: string;
  session_id?: string;
  message?: string;
  tool_name?: string;
  tool_call_id?: string;
  args?: string;
  result?: string;
  tool_traces?: { tool_name: string; args: string; result: string }[];
  usage?: { total_tokens: number };
  original_messages?: number;
  compacted_messages?: number;
  estimated_tokens_saved?: number;
  // Interaction request fields
  request_id?: string;
  kind?: string;
  prompt?: string;
  options?: string[];
  [key: string]: unknown;
}

/** Session detail from GET /sessions/:id */
export interface SessionDetail {
  id: string;
  title: string;
  model: string;
  workdir: string;
  message_count: number;
  created_at: string;
  updated_at: string;
  messages: { role: string; content: string; timestamp: string; images?: ImageAttachment[] }[];
}
