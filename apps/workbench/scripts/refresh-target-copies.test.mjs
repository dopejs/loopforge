import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { refreshTargetCopies } from "./refresh-target-copies.mjs";

/**
 * Putting a rebuilt sidecar where a development build runs it.
 *
 * `pnpm tauri dev` runs out of `src-tauri/target/<profile>/resources/`, and the
 * build scripts wrote to `resources/` and stopped there. So a rebuilt Kura
 * never reached the running app -- and because a Kura daemon forks and outlives
 * the app, restarting the app connected it straight back to the daemon the
 * rebuild was meant to replace. The fix was on disk and the bug was still
 * running, with nothing saying so.
 */
describe("refreshTargetCopies", () => {
  let root;

  beforeEach(() => {
    root = mkdtempSync(resolve(tmpdir(), "lf-refresh-"));
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  function existingCopy(profile, name, contents) {
    const directory = resolve(root, "src-tauri", "target", profile, "resources");
    mkdirSync(directory, { recursive: true });
    writeFileSync(resolve(directory, name), contents);
    return resolve(directory, name);
  }

  function built(name, contents) {
    const path = resolve(root, name);
    writeFileSync(path, contents);
    return path;
  }

  it("overwrites the copy a development build runs", () => {
    const stale = existingCopy("debug", "kura", "old");
    const fresh = built("kura", "new");

    const refreshed = refreshTargetCopies(root, fresh, "kura");

    expect(refreshed).toEqual([stale]);
    expect(readFileSync(stale, "utf8")).toBe("new");
  });

  it("refreshes every profile that has one", () => {
    // Someone who has built both keeps both, and the stale one is the one
    // they will run next.
    const debug = existingCopy("debug", "kura", "old");
    const release = existingCopy("release", "kura", "old");
    const fresh = built("kura", "new");

    refreshTargetCopies(root, fresh, "kura");

    expect(readFileSync(debug, "utf8")).toBe("new");
    expect(readFileSync(release, "utf8")).toBe("new");
  });

  it("creates nothing where nothing was built", () => {
    // A profile nobody has compiled has no resources directory, and inventing
    // one would leave a binary somewhere the build does not manage.
    mkdirSync(resolve(root, "src-tauri", "target", "debug"), { recursive: true });
    const fresh = built("kura", "new");

    expect(refreshTargetCopies(root, fresh, "kura")).toEqual([]);
  });

  it("does nothing at all when there is no target tree", () => {
    // A clean checkout, or a packaging build. Neither is a failure.
    const fresh = built("kura", "new");

    expect(refreshTargetCopies(root, fresh, "kura")).toEqual([]);
  });

  it("refreshes the sidecar it was given and leaves the other alone", () => {
    // Both live in the same directory. Refreshing the Agent must write the
    // Agent -- a first version of this refreshed Kura and asserted the Agent
    // was untouched, which is true even if the name is ignored entirely.
    const agent = existingCopy("debug", "loopforge-agent", "old-agent");
    const kura = existingCopy("debug", "kura", "old-kura");
    const fresh = built("loopforge-agent", "new-agent");

    const refreshed = refreshTargetCopies(root, fresh, "loopforge-agent");

    expect(refreshed).toEqual([agent]);
    expect(readFileSync(agent, "utf8")).toBe("new-agent");
    expect(readFileSync(kura, "utf8")).toBe("old-kura");
  });
});
