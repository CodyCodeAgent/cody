import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Web API routes
      "/api": "http://localhost:8000",
      // RPC routes (no /api prefix in backend)
      "/sessions": "http://localhost:8000",
      "/skills": "http://localhost:8000",
      "/config": "http://localhost:8000",
      "/run": "http://localhost:8000",
      "/tool": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/agents": "http://localhost:8000",
      "/audit": "http://localhost:8000",
      // WebSocket routes
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
