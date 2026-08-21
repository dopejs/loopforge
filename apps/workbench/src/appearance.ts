/**
 * Appearance preferences are Workbench-local and shared by every project, so
 * they live in localStorage rather than in a project's `.loopforge` directory.
 */

export const APPEARANCE_STORAGE_KEY = "loopforge.appearance";

export type ThemePreference = "dark" | "light" | "system";
export type ResolvedTheme = "dark" | "light";
export type Density = "compact" | "standard";

/** Accent swatches from the Workbench design. `id` is what gets persisted. */
export const ACCENTS = [
  { id: "ember", color: "#ff8a3d", ink: "#1c1004" },
  { id: "deepSpace", color: "#5b8cff", ink: "#04101c" },
  { id: "terminal", color: "#4ade80", ink: "#04180c" },
  { id: "neon", color: "#c084fc", ink: "#160424" }
] as const;

export type AccentId = (typeof ACCENTS)[number]["id"];

export type Appearance = {
  theme: ThemePreference;
  density: Density;
  accent: AccentId;
  /** Reopen the last project on launch. */
  restoreLastProject: boolean;
};

export const DEFAULT_APPEARANCE: Appearance = {
  theme: "dark",
  density: "standard",
  accent: "ember",
  restoreLastProject: true
};

function isAccent(value: unknown): value is AccentId {
  return ACCENTS.some((accent) => accent.id === value);
}

export function accentColor(accent: AccentId): string {
  return (ACCENTS.find((candidate) => candidate.id === accent) ?? ACCENTS[0]).color;
}

export function accentInk(accent: AccentId): string {
  return (ACCENTS.find((candidate) => candidate.id === accent) ?? ACCENTS[0]).ink;
}

/**
 * Reads stored preferences, ignoring any field that is missing or corrupt so a
 * partially-written value degrades to the default instead of breaking startup.
 */
export function loadAppearance(storage: Storage): Appearance {
  const serialized = storage.getItem(APPEARANCE_STORAGE_KEY);
  if (!serialized) return DEFAULT_APPEARANCE;
  let parsed: unknown;
  try {
    parsed = JSON.parse(serialized);
  } catch {
    return DEFAULT_APPEARANCE;
  }
  if (typeof parsed !== "object" || parsed === null) return DEFAULT_APPEARANCE;
  const candidate = parsed as Partial<Record<keyof Appearance, unknown>>;
  return {
    theme:
      candidate.theme === "dark" || candidate.theme === "light" || candidate.theme === "system"
        ? candidate.theme
        : DEFAULT_APPEARANCE.theme,
    density:
      candidate.density === "compact" || candidate.density === "standard"
        ? candidate.density
        : DEFAULT_APPEARANCE.density,
    accent: isAccent(candidate.accent) ? candidate.accent : DEFAULT_APPEARANCE.accent,
    restoreLastProject:
      typeof candidate.restoreLastProject === "boolean"
        ? candidate.restoreLastProject
        : DEFAULT_APPEARANCE.restoreLastProject
  };
}

export function saveAppearance(storage: Storage, appearance: Appearance): void {
  storage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(appearance));
}

export function resolveTheme(theme: ThemePreference, systemPrefersDark: boolean): ResolvedTheme {
  if (theme === "system") return systemPrefersDark ? "dark" : "light";
  return theme;
}
