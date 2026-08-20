import { execFileSync } from "node:child_process";
import { chmodSync, mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(desktopRoot, "..", "..");
const entrypoint = resolve(repositoryRoot, "agent", "loopforge_agent", "__main__.py");
const resourcesRoot = resolve(desktopRoot, "resources");
const cacheRoot = resolve(desktopRoot, ".cache", "agent-build");
const binaryName = process.platform === "win32" ? "loopforge-agent.exe" : "loopforge-agent";
const binary = resolve(resourcesRoot, binaryName);
const dataSeparator = process.platform === "win32" ? ";" : ":";

statSync(entrypoint);
mkdirSync(resourcesRoot, { recursive: true });
mkdirSync(cacheRoot, { recursive: true });

execFileSync(
  "uv",
  [
    "run",
    "--with",
    "pyinstaller==6.22.2",
    "pyinstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "loopforge-agent",
    "--paths",
    resolve(repositoryRoot, "agent"),
    "--paths",
    resolve(repositoryRoot, "cli"),
    "--add-data",
    `${resolve(repositoryRoot, "skills")}${dataSeparator}loopforge_agent/_bundled_skills`,
    "--distpath",
    resourcesRoot,
    "--workpath",
    resolve(cacheRoot, "work"),
    "--specpath",
    resolve(cacheRoot, "spec"),
    entrypoint
  ],
  { cwd: repositoryRoot, stdio: "inherit" }
);

if (process.platform !== "win32") chmodSync(binary, 0o755);
console.log(`Bundled Loopforge Agent: ${binary}`);
