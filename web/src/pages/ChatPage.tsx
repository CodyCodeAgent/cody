import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getProject } from "../api/client";
import type { Project } from "../types";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";

export default function ChatPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    getProject(projectId)
      .then(setProject)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [projectId]);

  if (!projectId) {
    return <div>No project selected</div>;
  }

  return (
    <div className="chat-page">
      <Sidebar currentProjectId={projectId} />
      <main className="chat-main">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : project ? (
          <ChatWindow projectId={project.id} projectName={project.name} />
        ) : (
          <div className="loading">Project not found</div>
        )}
      </main>
    </div>
  );
}
