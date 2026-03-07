import { useEffect, useState } from "react";
import { getConfig, updateConfig } from "../api/client";
import Sidebar from "../components/Sidebar";

export default function SettingsPage() {
  const [model, setModel] = useState("");
  const [modelBaseUrl, setModelBaseUrl] = useState("");
  const [modelApiKey, setModelApiKey] = useState("");
  const [enableThinking, setEnableThinking] = useState(false);
  const [thinkingBudget, setThinkingBudget] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setModel((cfg.model as string) ?? "");
        setModelBaseUrl((cfg.model_base_url as string) ?? "");
        setModelApiKey((cfg.model_api_key as string) ?? "");
        setEnableThinking((cfg.enable_thinking as boolean) ?? false);
        setThinkingBudget(
          cfg.thinking_budget != null ? String(cfg.thinking_budget) : ""
        );
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage("");
    try {
      const data: Record<string, unknown> = {};
      if (model) data.model = model;
      if (modelBaseUrl) data.model_base_url = modelBaseUrl;
      if (modelApiKey) data.model_api_key = modelApiKey;
      data.enable_thinking = enableThinking;
      if (thinkingBudget) data.thinking_budget = parseInt(thinkingBudget, 10);

      await updateConfig(data as Parameters<typeof updateConfig>[0]);
      setMessage("Settings saved");
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="chat-page">
      <Sidebar />
      <main className="chat-main">
        <div className="manage-page">
          <h2>Settings</h2>
          {loading ? (
            <div className="loading">Loading...</div>
          ) : (
            <div className="settings-form">
              <label className="settings-field">
                <span>Model</span>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="anthropic:claude-sonnet-4-0"
                />
              </label>

              <label className="settings-field">
                <span>Model Base URL</span>
                <input
                  type="text"
                  value={modelBaseUrl}
                  onChange={(e) => setModelBaseUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                />
              </label>

              <label className="settings-field">
                <span>API Key</span>
                <input
                  type="password"
                  value={modelApiKey}
                  onChange={(e) => setModelApiKey(e.target.value)}
                  placeholder="sk-..."
                />
              </label>

              <label className="settings-field settings-field-inline">
                <span>Enable Thinking</span>
                <input
                  type="checkbox"
                  checked={enableThinking}
                  onChange={(e) => setEnableThinking(e.target.checked)}
                />
              </label>

              {enableThinking && (
                <label className="settings-field">
                  <span>Thinking Budget (tokens)</span>
                  <input
                    type="number"
                    value={thinkingBudget}
                    onChange={(e) => setThinkingBudget(e.target.value)}
                    placeholder="10000"
                  />
                </label>
              )}

              <div className="settings-actions">
                <button
                  className="btn btn-primary"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Save"}
                </button>
                {message && (
                  <span className={message.startsWith("Error") ? "settings-error" : "settings-success"}>
                    {message}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
