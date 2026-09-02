import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const submoduleRoot = resolve(desktopRoot, "vendor", "kura");
const manifest = resolve(submoduleRoot, "crates", "Cargo.toml");
const targetBinary = resolve(submoduleRoot, "crates", "target", "release", process.platform === "win32" ? "kura.exe" : "kura");
const resourcesRoot = resolve(desktopRoot, "resources");
const bundledBinary = resolve(resourcesRoot, process.platform === "win32" ? "kura.exe" : "kura");

try {
  statSync(manifest);
} catch {
  throw new Error("Kura submodule is not initialized; run `git submodule update --init --recursive`");
}

execFileSync("cargo", ["build", "--release", "-p", "kura-cli", "--manifest-path", manifest], {
  cwd: submoduleRoot,
  stdio: "inherit"
});
mkdirSync(resourcesRoot, { recursive: true });
copyFileSync(targetBinary, bundledBinary);
if (process.platform !== "win32") execFileSync("chmod", ["0755", bundledBinary]);

// Stamp the submodule commit next to the binary. `dev.sh` reuses a bundled
// sidecar to keep the frontend loop fast, and without this it cannot tell a
// current binary from one built before a submodule bump -- which fails
// silently rather than loudly when the daemon's contract has changed.
const builtCommit = execFileSync("git", ["rev-parse", "HEAD"], {
  cwd: submoduleRoot,
  encoding: "utf8"
}).trim();
writeFileSync(resolve(resourcesRoot, "kura.build.json"), `${JSON.stringify({ commit: builtCommit }, null, 2)}\n`);
// Re-sign on macOS, or the kernel kills the binary on launch.
//
// Copying a freshly built binary over the same path leaves macOS holding a
// stale signature for it: the file verifies, and the kernel still refuses to
// execute it, killing the process with SIGKILL before it writes a byte. From
// the outside that is a daemon that "failed to start" with empty stdout and
// stderr, which says nothing about why -- the agent script has carried this
// fix since the sidecar hit it, and the daemon reaches the same kernel.
if (process.platform === "darwin") {
  execFileSync("codesign", ["--force", "--sign", "-", bundledBinary], { stdio: "inherit" });
  // Verified rather than assumed: a signature that does not actually let the
  // binary run is the exact failure this exists to prevent, and it is
  // invisible until something tries to run it.
  execFileSync(bundledBinary, ["--help"], { stdio: "ignore" });
}

console.log(`Bundled Kura daemon (kura) from ${builtCommit.slice(0, 7)}: ${bundledBinary}`);

// The binary is copied before Tauri packaging, so the large Cargo target is
// disposable and never becomes part of the desktop source tree.
if (process.env.LOOPFORGE_KEEP_DAEMON_TARGET !== "1") {
  rmSync(resolve(submoduleRoot, "crates", "target"), { recursive: true, force: true });
}
