import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, rmSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const submoduleRoot = resolve(desktopRoot, "vendor", "kura");
const manifest = resolve(submoduleRoot, "crates", "Cargo.toml");
const targetBinary = resolve(submoduleRoot, "crates", "target", "release", process.platform === "win32" ? "dope-cli.exe" : "dope-cli");
const resourcesRoot = resolve(desktopRoot, "resources");
const bundledBinary = resolve(resourcesRoot, process.platform === "win32" ? "dope-cli.exe" : "dope-cli");

try {
  statSync(manifest);
} catch {
  throw new Error("Kura submodule is not initialized; run `git submodule update --init --recursive`");
}

execFileSync("cargo", ["build", "--release", "-p", "dope-cli", "--manifest-path", manifest], {
  cwd: submoduleRoot,
  stdio: "inherit"
});
mkdirSync(resourcesRoot, { recursive: true });
copyFileSync(targetBinary, bundledBinary);
if (process.platform !== "win32") execFileSync("chmod", ["0755", bundledBinary]);
console.log(`Bundled Kura daemon (dope-cli): ${bundledBinary}`);

// The binary is copied before Tauri packaging, so the large Cargo target is
// disposable and never becomes part of the desktop source tree.
if (process.env.LOOPFORGE_KEEP_DAEMON_TARGET !== "1") {
  rmSync(resolve(submoduleRoot, "crates", "target"), { recursive: true, force: true });
}
