import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento, /api vai para a API local (uvicorn na porta 8000).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist", sourcemap: true },
});
