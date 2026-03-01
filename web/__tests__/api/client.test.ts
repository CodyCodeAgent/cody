import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  healthCheck,
  listDirectories,
  initProject,
  listSessions,
  createSession,
  getSession,
  deleteSession,
} from "../../src/api/client";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: () => Promise.resolve(data),
  });
}

function errorResponse(code: string, message: string, status = 400) {
  return Promise.resolve({
    ok: false,
    status,
    statusText: "Bad Request",
    json: () => Promise.resolve({ error: { code, message } }),
  });
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe("healthCheck", () => {
  it("calls GET /health and returns data", async () => {
    mockFetch.mockReturnValue(jsonResponse({ status: "ok", version: "1.3.0" }));
    const data = await healthCheck();
    expect(data.status).toBe("ok");
    expect(data.version).toBe("1.3.0");
    expect(mockFetch).toHaveBeenCalledWith("/health", undefined);
  });
});

describe("listDirectories", () => {
  it("calls GET /api/directories without params", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ path: "/home/user", entries: [] })
    );
    const data = await listDirectories();
    expect(data.path).toBe("/home/user");
    expect(mockFetch).toHaveBeenCalledWith("/api/directories", undefined);
  });

  it("passes path as query param", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ path: "/tmp", entries: [{ name: "foo", is_dir: true }] })
    );
    const data = await listDirectories("/tmp");
    expect(data.entries).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/directories?path=%2Ftmp",
      undefined
    );
  });
});

describe("initProject", () => {
  it("sends POST /api/projects/init with workdir", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ status: "success", workdir: "/home/user/proj" })
    );
    const data = await initProject("/home/user/proj");
    expect(data.status).toBe("success");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects/init", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workdir: "/home/user/proj" }),
    });
  });
});

describe("listSessions", () => {
  it("returns sessions array", async () => {
    mockFetch.mockReturnValue(jsonResponse({ sessions: [{ id: "abc" }] }));
    const sessions = await listSessions();
    expect(sessions).toHaveLength(1);
    expect(sessions[0].id).toBe("abc");
  });
});

describe("createSession", () => {
  it("sends POST /sessions with query params", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ id: "new123", title: "My Chat" })
    );
    await createSession("My Chat", "/tmp");
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toContain("/sessions?");
    expect(url).toContain("title=My+Chat");
    expect(opts.method).toBe("POST");
  });
});

describe("getSession", () => {
  it("calls GET /sessions/:id", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ id: "s1", messages: [{ role: "user", content: "hi" }] })
    );
    const data = await getSession("s1");
    expect(data.id).toBe("s1");
    expect(mockFetch).toHaveBeenCalledWith("/sessions/s1", undefined);
  });
});

describe("deleteSession", () => {
  it("calls DELETE /sessions/:id", async () => {
    mockFetch.mockReturnValue(jsonResponse({ status: "deleted" }));
    const data = await deleteSession("s1");
    expect(data.status).toBe("deleted");
    expect(mockFetch).toHaveBeenCalledWith("/sessions/s1", {
      method: "DELETE",
    });
  });
});

describe("error handling", () => {
  it("throws with error message from response body", async () => {
    mockFetch.mockReturnValue(
      errorResponse("INVALID_PARAMS", "path is required", 400)
    );
    await expect(healthCheck()).rejects.toThrow("path is required");
  });
});
