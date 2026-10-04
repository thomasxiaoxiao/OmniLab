import { defineConfig } from "vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  build: {
    outDir: "../src/hacknation_databricks/web/static",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: 8000,
    strictPort: true,
    fs: {
      allow: [
        fileURLToPath(new URL(".", import.meta.url)),
        fileURLToPath(new URL("../node_modules", import.meta.url)),
      ],
    },
    proxy: {
      "/api": { target: "http://127.0.0.1:8011", changeOrigin: false },
      "/health": { target: "http://127.0.0.1:8011", changeOrigin: false },
    },
  },
});
