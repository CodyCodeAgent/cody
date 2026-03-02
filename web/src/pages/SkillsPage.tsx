import { useEffect, useState } from "react";
import { listSkills, enableSkill, disableSkill } from "../api/client";
import type { SkillInfo } from "../api/client";
import Sidebar from "../components/Sidebar";

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listSkills()
      .then((res) => setSkills(res.skills))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (name: string, currentlyEnabled: boolean) => {
    try {
      if (currentlyEnabled) {
        await disableSkill(name);
      } else {
        await enableSkill(name);
      }
      setSkills((prev) =>
        prev.map((s) =>
          s.name === name ? { ...s, enabled: !currentlyEnabled } : s
        )
      );
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="chat-page">
      <Sidebar />
      <main className="chat-main">
        <div className="manage-page">
          <h2>Skills</h2>
          {loading ? (
            <div className="loading">Loading...</div>
          ) : (
            <div className="skills-list">
              {skills.map((skill) => (
                <div key={skill.name} className="skill-card">
                  <div className="skill-info">
                    <span className="skill-name">{skill.name}</span>
                    <span className="skill-source">{skill.source}</span>
                    <p className="skill-desc">{skill.description}</p>
                  </div>
                  <button
                    className={`btn btn-sm ${skill.enabled ? "btn-primary" : ""}`}
                    onClick={() => handleToggle(skill.name, skill.enabled)}
                  >
                    {skill.enabled ? "Enabled" : "Disabled"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
