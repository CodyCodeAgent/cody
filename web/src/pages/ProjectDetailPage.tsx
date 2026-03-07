import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProject,
  listTasks,
  createTask,
  deleteTask,
} from "../api/client";
import type { Project, Task } from "../types";
import Sidebar from "../components/Sidebar";

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  // New task form
  const [showNewTask, setShowNewTask] = useState(false);
  const [taskName, setTaskName] = useState("");
  const [branchName, setBranchName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [p, t] = await Promise.all([
        getProject(projectId),
        listTasks(projectId),
      ]);
      setProject(p);
      setTasks(t);
    } catch (e) {
      console.error("Failed to load project:", e);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleCreateTask() {
    if (!projectId || !taskName.trim() || !branchName.trim()) {
      setError("Task name and branch name are required");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const task = await createTask(projectId, taskName.trim(), branchName.trim());
      setTasks((prev) => [task, ...prev]);
      setShowNewTask(false);
      setTaskName("");
      setBranchName("");
      // Navigate to the task chat
      navigate(`/task/${task.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create task");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteTask(taskId: string) {
    if (!window.confirm("Delete this task?")) return;
    try {
      await deleteTask(taskId);
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    } catch (e) {
      console.error("Delete failed:", e);
    }
  }

  if (!projectId) return <div>No project selected</div>;

  return (
    <div className="chat-page">
      <Sidebar currentProjectId={projectId} />
      <main className="chat-main">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : !project ? (
          <div className="loading">Project not found</div>
        ) : (
          <div className="project-detail">
            <div className="project-detail-header">
              <div>
                <h2>{project.name}</h2>
                {project.description && (
                  <p className="project-description">{project.description}</p>
                )}
                <div className="project-meta">
                  <span className="project-meta-label">Working Directory:</span>
                  <code>{project.workdir}</code>
                </div>
                {project.code_paths.length > 0 && (
                  <div className="project-meta">
                    <span className="project-meta-label">Code Paths:</span>
                    <div className="project-code-paths">
                      {project.code_paths.map((cp, i) => (
                        <code key={i}>{cp}</code>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <button
                className="btn btn-primary"
                onClick={() => navigate(`/chat/${project.id}`)}
              >
                Project Chat
              </button>
            </div>

            <div className="tasks-section">
              <div className="tasks-header">
                <h3>Development Tasks</h3>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setShowNewTask(true)}
                >
                  + New Task
                </button>
              </div>

              {showNewTask && (
                <div className="new-task-form">
                  <div className="wizard-fields">
                    <label>
                      Task Name
                      <input
                        type="text"
                        value={taskName}
                        onChange={(e) => setTaskName(e.target.value)}
                        placeholder="e.g. Add user authentication"
                      />
                    </label>
                    <label>
                      Branch Name
                      <input
                        type="text"
                        value={branchName}
                        onChange={(e) => setBranchName(e.target.value)}
                        placeholder="e.g. feature/auth"
                      />
                    </label>
                  </div>
                  {error && <div className="wizard-error">{error}</div>}
                  <div className="new-task-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={handleCreateTask}
                      disabled={creating || !taskName.trim() || !branchName.trim()}
                    >
                      {creating ? "Creating..." : "Create & Start"}
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={() => {
                        setShowNewTask(false);
                        setError("");
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {tasks.length === 0 && !showNewTask && (
                <div className="tasks-empty">
                  No tasks yet. Create a new development task to start coding.
                </div>
              )}

              <div className="tasks-list">
                {tasks.map((task) => (
                  <div key={task.id} className="task-card">
                    <div className="task-info">
                      <button
                        className="task-name-link"
                        onClick={() => navigate(`/task/${task.id}`)}
                      >
                        {task.name}
                      </button>
                      <div className="task-meta">
                        <span className="task-branch">{task.branch_name}</span>
                        <span className={`task-status task-status-${task.status}`}>
                          {task.status}
                        </span>
                      </div>
                    </div>
                    <div className="task-actions">
                      <button
                        className="btn btn-sm"
                        onClick={() => navigate(`/task/${task.id}`)}
                      >
                        Open
                      </button>
                      <button
                        className="btn-icon delete-btn"
                        onClick={() => handleDeleteTask(task.id)}
                        title="Delete task"
                      >
                        &times;
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
