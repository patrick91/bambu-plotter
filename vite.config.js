import { defineConfig } from "vite";
import inertia from "@inertiajs/vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [tailwindcss(), react(), inertia()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./frontend", import.meta.url)),
    },
  },
  build: {
    manifest: true,
    outDir: "static/build",
    rollupOptions: {
      input: "frontend/app.tsx",
    },
  },
});
