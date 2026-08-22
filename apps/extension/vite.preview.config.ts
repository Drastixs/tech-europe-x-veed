import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const dirname = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  define: {
    "process.env.NODE_ENV": JSON.stringify("production")
  },
  build: {
    emptyOutDir: true,
    outDir: "preview-dist",
    lib: {
      entry: resolve(dirname, "src/preview-entry.tsx"),
      formats: ["iife"],
      name: "OnshapeAssistPreview",
      fileName: () => "overlay-preview.js"
    },
    minify: false
  }
});
