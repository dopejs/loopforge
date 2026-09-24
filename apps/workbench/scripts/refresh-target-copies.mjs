import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Put a freshly built binary where a development build actually runs it.
 *
 * `pnpm tauri dev` runs out of `src-tauri/target/<profile>/resources/`, not out
 * of `resources/`. Rebuilding a sidecar wrote the new binary to the latter and
 * left the former alone, so the running app kept the old one -- and because a
 * Kura daemon forks and outlives the app, restarting the app connected it
 * straight back to the daemon the rebuild was meant to replace. The fix was on
 * disk and the bug was still running, with nothing saying so.
 *
 * Copies rather than deletes: deleting would leave a development build with no
 * sidecar until someone rebuilt the Rust, which is slower than the thing they
 * were trying to test.
 *
 * Signed after copying, on macOS, for the reason the build scripts sign their
 * own output -- a binary replaced at a path the kernel has already executed
 * keeps the old inode's signature and is killed outright, while `codesign
 * --verify` still calls the file valid.
 */
export function refreshTargetCopies(desktopRoot, sourceBinary, binaryName) {
  const targets = resolve(desktopRoot, "src-tauri", "target");
  if (!existsSync(targets)) return [];
  const refreshed = [];
  for (const profile of readdirSync(targets)) {
    const destination = resolve(targets, profile, "resources", binaryName);
    if (!existsSync(destination)) continue;
    copyFileSync(sourceBinary, destination);
    if (process.platform === "darwin") {
      execFileSync("codesign", ["--force", "--sign", "-", destination], { stdio: "inherit" });
    }
    refreshed.push(destination);
  }
  return refreshed;
}
