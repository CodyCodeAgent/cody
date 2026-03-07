import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getTask, getProject } from "../api/client";
import type { Project, Task } from "../types";
import Sidebar from "../components/Sidebar";
import TaskChatWindow from "../components/TaskChatWindow";

export default function TaskChatPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [task, setTask] = useState<Task | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    getTask(taskId)
      .then(async (t) => {
        setTask(t);
        const p = await getProject(t.project_id);
        setProject(p);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [taskId]);

  if (!taskId) return <div>No task selected</div>;

  return (
    <div className="chat-page">
      <Sidebar currentProjectId={project?.id} />
      <main className="chat-main">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : task && project ? (
          <TaskChatWindow
            taskId={task.id}
            taskName={task.name}
            branchName={task.branch_name}
            projectName={project.name}
            projectId={project.id}
            sessionId={task.session_id}
          />
        ) : (
          <div className="loading">Task not found</div>
        )}
      </main>
    </div>
  );
}
