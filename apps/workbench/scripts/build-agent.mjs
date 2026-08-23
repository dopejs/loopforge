import { execFileSync } from "node:child_process";
import { chmodSync, mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(desktopRoot, "..", "..");
const agentRoot = resolve(repositoryRoot, "apps", "agent");
const entrypoint = resolve(agentRoot, "loopforge_agent", "__main__.py");
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
    agentRoot,
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

// Re-sign on macOS, or the kernel kills the binary on launch.
//
// PyInstaller writes its own ad-hoc signature, but rebuilding over the same
// path leaves macOS holding a stale one: `codesign --verify` reports the file
// as valid while the kernel refuses to execute it, killing the process with
// SIGKILL and "Taskgated Invalid Signature" before it can print anything.
//
// The failure is silent from the app's side -- the sidecar simply never comes
// up -- so the shell falls back to whatever agent is still listening from an
// earlier build, and a fix stops reaching the user entirely. That is worth
// one signing call per build.
if (process.platform === "darwin") {
  execFileSync("codesign", ["--force", "--sign", "-", binary], { stdio: "inherit" });
  // Verified rather than assumed: a signature that does not actually let the
  // binary run is the exact failure this exists to prevent.
  execFileSync(binary, ["--help"], { stdio: "ignore" });
}

console.log(`Bundled Loopforge Agent: ${binary}`);
