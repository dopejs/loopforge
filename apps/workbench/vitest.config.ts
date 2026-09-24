import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // `scripts/` is included because the build scripts are code that runs on
    // every developer's machine and one of them silently shipped a rebuilt
    // daemon to a path nothing executed. Untested build tooling is tooling
    // whose failures are found by a person wondering why their fix did nothing.
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "scripts/**/*.test.mjs"]
  }
});
