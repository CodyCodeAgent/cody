import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ChatPage from "./pages/ChatPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import TaskChatPage from "./pages/TaskChatPage";
import SkillsPage from "./pages/SkillsPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/project/:projectId" element={<ProjectDetailPage />} />
        <Route path="/chat/:projectId" element={<ChatPage />} />
        <Route path="/task/:taskId" element={<TaskChatPage />} />
        <Route path="/skills" element={<SkillsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
