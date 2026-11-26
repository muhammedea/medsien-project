import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development, /api is forwarded to the backend running locally (uvicorn on :8000).
// In Docker, nginx does the same forwarding (see nginx.conf).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
