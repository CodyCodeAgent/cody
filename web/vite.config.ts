import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/run": "http://localhost:8000",
      "/tool": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/sessions": "http://localhost:8000",
      "/skills": "http://localhost:8000",
      "/audit": "http://localhost:8000",
      "/agent": "http://localhost:8000",
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
