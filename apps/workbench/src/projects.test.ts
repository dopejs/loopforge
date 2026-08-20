import { describe, expect, it } from "vitest";
import {
  addProjectRoot,
  loadActiveProject,
  loadProjectRoots,
  projectName,
  saveProjectSelection
} from "./projects";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

describe("Workbench projects", () => {
  it("migrates the previous active project into the project list", () => {
    const storage = new MemoryStorage();
    storage.setItem("loopforge.projectRoot", "/games/one");
    storage.setItem("loopforge.projectRoots", JSON.stringify(["/games/two"]));

    expect(loadProjectRoots(storage)).toEqual(["/games/one", "/games/two"]);
  });

  it("rejects malformed storage and deduplicates added projects", () => {
    const storage = new MemoryStorage();
    storage.setItem("loopforge.projectRoots", "not-json");

    expect(loadProjectRoots(storage)).toEqual([]);
    expect(addProjectRoot(["/games/one"], "/games/one")).toEqual(["/games/one"]);
  });

  it("persists the active project and derives a compact label", () => {
    const storage = new MemoryStorage();
    saveProjectSelection(storage, ["/games/one"], "/games/one");
    const roots = loadProjectRoots(storage);

    expect(loadActiveProject(storage, roots)).toBe("/games/one");
    expect(projectName("/games/one/")).toBe("one");
  });
});
