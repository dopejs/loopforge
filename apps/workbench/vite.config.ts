import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const { version } = JSON.parse(
  readFileSync(fileURLToPath(new URL("./package.json", import.meta.url)), "utf8")
) as { version: string };

export default defineConfig({
  plugins: [react()],
  define: {
    // Surfaced in Settings › About so the shipped build reports its real version.
    __APP_VERSION__: JSON.stringify(version)
  },
  server: { port: 1420, strictPort: true },
  clearScreen: false
});
