import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { isDesktopRuntime } from "./agent";

/**
 * Local storage here is a startup cache, not the record.
 *
 * The list is read synchronously in App's initial state -- it decides which
 * project to reopen before anything renders -- and reading the user store is
 * an async call into the shell. Without a cache the window would show an empty
 * workspace for a frame and then replace it, which is worse than a list that
 * is briefly one launch out of date. The store overwrites it as soon as it
 * answers.
 */
const PROJECTS_STORAGE_KEY = "loopforge.projectRoots";
const ACTIVE_PROJECT_STORAGE_KEY = "loopforge.projectRoot";

export function loadProjectRoots(storage: Storage): string[] {
  const savedActive = storage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
  const serialized = storage.getItem(PROJECTS_STORAGE_KEY);
  let roots: string[] = [];
  if (serialized) {
    try {
      const parsed: unknown = JSON.parse(serialized);
      if (Array.isArray(parsed)) {
        roots = parsed.filter(
          (value): value is string => typeof value === "string" && value.length > 0
        );
      }
    } catch {
      roots = [];
    }
  }
  return uniqueProjectRoots(savedActive ? [savedActive, ...roots] : roots);
}

export function loadActiveProject(storage: Storage, roots: string[]): string {
  const saved = storage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
  return saved && roots.includes(saved) ? saved : roots[0] ?? "";
}

export function saveProjectSelection(
  storage: Storage,
  roots: string[],
  activeProject: string
): void {
  storage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(uniqueProjectRoots(roots)));
  if (activeProject) {
    storage.setItem(ACTIVE_PROJECT_STORAGE_KEY, activeProject);
  } else {
    storage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
  }
}

export function addProjectRoot(roots: string[], root: string): string[] {
  return uniqueProjectRoots([...roots, root]);
}

export function projectName(root: string): string {
  const normalized = root.replace(/[\\/]+$/, "");
  return normalized.split(/[\\/]/).pop() || root;
}

function uniqueProjectRoots(roots: string[]): string[] {
  return [...new Set(roots.filter((root) => root.length > 0))];
}

/** Mirrors the `projects` table the Agent defines. */
export type RecentProject = {
  path: string;
  last_opened_at: string;
  last_mode: string;
};

/**
 * The authoritative recent list, from `~/.loopforge`.
 *
 * Read from the shell rather than the Agent: an Agent is started per project,
 * so asking one which projects exist is circular, and this is needed before
 * any project is open.
 */
export function useRecentProjects(): { projects: readonly RecentProject[]; loaded: boolean } {
  const [projects, setProjects] = useState<readonly RecentProject[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!isDesktopRuntime()) {
      setLoaded(true);
      return;
    }
    let cancelled = false;
    void invoke<RecentProject[]>("recent_projects")
      .then((result) => {
        if (!cancelled) setProjects(result ?? []);
      })
      .catch(() => {
        // A convenience, not a record: an unreadable store leaves the cached
        // list in place rather than emptying the window.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { projects, loaded };
}

/** Records that a project was opened. Failure is not surfaced. */
export function rememberProject(root: string, mode: string): void {
  if (!isDesktopRuntime() || !root) return;
  void invoke("remember_project", { projectPath: root, mode }).catch(() => {
    // Recording the visit must never be what stops a project from opening.
  });
}

export function forgetProject(root: string): void {
  if (!isDesktopRuntime() || !root) return;
  void invoke("forget_project", { projectPath: root }).catch(() => {});
}
