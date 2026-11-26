import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api is forwarded to the backend running locally (uvicorn on :8000).
// In Docker, nginx does the same forwarding (see nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
