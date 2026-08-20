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
