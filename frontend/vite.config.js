import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
const backend = process.env.NEXUSAI_PREVIEW_BACKEND || "http://127.0.0.1:8000"
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(backend)) throw new Error("Loopback backend required")
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": backend,
      "/ws": { target: backend.replace("http:","ws:"), ws: true }
    }
  }
})
