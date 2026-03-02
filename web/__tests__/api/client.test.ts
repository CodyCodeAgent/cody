import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  healthCheck,
  listDirectories,
  listProjects,
  createProject,
  getProject,
  updateProject,
  deleteProject,
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

function errorResponse(detail: string, status = 400) {
  return Promise.resolve({
    ok: false,
    status,
    statusText: "Bad Request",
    json: () => Promise.resolve({ detail }),
  });
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe("healthCheck", () => {
  it("calls GET /api/health and returns data", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ status: "ok", version: "1.3.0", core_server: "connected" })
    );
    const data = await healthCheck();
    expect(data.status).toBe("ok");
    expect(data.version).toBe("1.3.0");
    expect(mockFetch).toHaveBeenCalledWith("/api/health", undefined);
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

describe("listProjects", () => {
  it("calls GET /api/projects", async () => {
    mockFetch.mockReturnValue(
      jsonResponse([{ id: "abc", name: "My Project" }])
    );
    const projects = await listProjects();
    expect(projects).toHaveLength(1);
    expect(projects[0].name).toBe("My Project");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects", undefined);
  });
});

describe("createProject", () => {
  it("sends POST /api/projects with JSON body", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ id: "new123", name: "Test", workdir: "/tmp" })
    );
    const project = await createProject("Test", "/tmp", "A description");
    expect(project.id).toBe("new123");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Test",
        workdir: "/tmp",
        description: "A description",
      }),
    });
  });

  it("defaults description to empty string", async () => {
    mockFetch.mockReturnValue(jsonResponse({ id: "x", name: "T" }));
    await createProject("T", "/tmp");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.description).toBe("");
  });
});

describe("getProject", () => {
  it("calls GET /api/projects/:id", async () => {
    mockFetch.mockReturnValue(jsonResponse({ id: "p1", name: "Proj" }));
    const data = await getProject("p1");
    expect(data.id).toBe("p1");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects/p1", undefined);
  });
});

describe("updateProject", () => {
  it("sends PUT /api/projects/:id", async () => {
    mockFetch.mockReturnValue(
      jsonResponse({ id: "p1", name: "Updated" })
    );
    const data = await updateProject("p1", { name: "Updated" });
    expect(data.name).toBe("Updated");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects/p1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Updated" }),
    });
  });
});

describe("deleteProject", () => {
  it("calls DELETE /api/projects/:id", async () => {
    mockFetch.mockReturnValue(jsonResponse({ status: "deleted" }));
    const data = await deleteProject("p1");
    expect(data.status).toBe("deleted");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects/p1", {
      method: "DELETE",
    });
  });
});

describe("error handling", () => {
  it("throws with detail from response body", async () => {
    mockFetch.mockReturnValue(errorResponse("path is required", 400));
    await expect(healthCheck()).rejects.toThrow("path is required");
  });
});
