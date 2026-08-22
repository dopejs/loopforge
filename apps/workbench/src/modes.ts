import type { MessageKey } from "./i18n/locales/en";

/** Workspaces in icon-rail order, matching the Workbench design. */
export const WORKSPACE_MODES = [
  "canvas",
  "flow",
  "test",
  "chat",
  "diff",
  "terminal",
  "tasks",
  "assets",
  "profiler"
] as const;

export type WorkspaceMode = (typeof WORKSPACE_MODES)[number];

/** `settings` is a full-screen view rather than a workspace, so it is separate. */
export type Mode = WorkspaceMode | "settings";

export function isWorkspaceMode(value: Mode): value is WorkspaceMode {
  return (WORKSPACE_MODES as readonly string[]).includes(value);
}

export function modeLabelKey(mode: Mode): MessageKey {
  return `mode.${mode}` as MessageKey;
}

export function modeDescriptionKey(mode: WorkspaceMode): MessageKey {
  return `mode.${mode}.description` as MessageKey;
}

export function sidebarTitleKey(mode: WorkspaceMode): MessageKey {
  return `sidebar.${mode}` as MessageKey;
}

/**
 * The workspaces backed by a Loopforge Agent endpoint.
 *
 * The rest render the full designed UI driven by placeholder data from
 * ../fixtures.ts, and Workspace.tsx uses this set to decide whether to show the
 * preview banner. Move a mode in here once the Agent serves its data, and swap
 * that workspace's fixture import for the real source.
 */
const WIRED_MODES: ReadonlySet<WorkspaceMode> = new Set<WorkspaceMode>([
  "chat",
  "terminal",
  "test",
  "tasks"
]);

export function isWired(mode: WorkspaceMode): boolean {
  return WIRED_MODES.has(mode);
}

/**
 * Cycles through the workspace ring. `settings` is not in the ring, so it steps
 * relative to the first workspace. Deltas of any magnitude or sign are wrapped:
 * JavaScript's `%` keeps the sign of the dividend, so a plain remainder would
 * index out of bounds for deltas below `-WORKSPACE_MODES.length`.
 */
export function stepMode(current: Mode, delta: number): WorkspaceMode {
  const count = WORKSPACE_MODES.length;
  const index = WORKSPACE_MODES.indexOf(current as WorkspaceMode);
  const from = index === -1 ? 0 : index;
  const next = (((from + delta) % count) + count) % count;
  return WORKSPACE_MODES[next];
}
