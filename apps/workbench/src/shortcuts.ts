import type { MessageKey } from "./i18n/locales/en";

export type ShortcutId =
  | "nextMode"
  | "previousMode"
  | "focusComposer"
  | "projectMenu"
  | "settings"
  | "toggleAgentPanel";

export type Shortcut = {
  id: ShortcutId;
  labelKey: MessageKey;
  /** Key as reported by `KeyboardEvent.key`, compared case-insensitively. */
  key: string;
  shift?: boolean;
  /** Display form; the primary modifier renders as ⌘ on Apple platforms. */
  display: readonly string[];
};

/**
 * Single source of truth for the shortcuts the Workbench actually handles. The
 * settings list renders from this array, so it can never advertise a binding
 * that no handler implements.
 *
 * Every binding uses the platform's primary modifier (⌘ on macOS, Ctrl
 * elsewhere) to stay clear of text-editing keys inside the composer.
 */
export const SHORTCUTS: readonly Shortcut[] = [
  { id: "nextMode", labelKey: "shortcut.nextMode", key: "]", display: ["mod", "]"] },
  { id: "previousMode", labelKey: "shortcut.previousMode", key: "[", display: ["mod", "["] },
  { id: "focusComposer", labelKey: "shortcut.focusComposer", key: "k", display: ["mod", "K"] },
  { id: "projectMenu", labelKey: "shortcut.projectMenu", key: "p", display: ["mod", "P"] },
  { id: "settings", labelKey: "shortcut.settings", key: ",", display: ["mod", ","] },
  {
    id: "toggleAgentPanel",
    labelKey: "shortcut.toggleAgentPanel",
    key: "\\",
    display: ["mod", "\\"]
  }
];

export function isApplePlatform(platform: string): boolean {
  return /mac|iphone|ipad|ipod/i.test(platform);
}

export function modifierSymbol(apple: boolean): string {
  return apple ? "⌘" : "Ctrl";
}

export function displayShortcut(shortcut: Shortcut, apple: boolean): string {
  return shortcut.display
    .map((part) => (part === "mod" ? modifierSymbol(apple) : part))
    .join(apple ? " " : " + ");
}

export type ShortcutEvent = {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
};

/**
 * Matches a keyboard event to a shortcut. macOS uses ⌘ and other platforms use
 * Ctrl; accepting either would make ⌃K on macOS (move-to-end-of-line in Cocoa
 * text fields) steal focus, so the primary modifier is platform-exact.
 */
export function matchShortcut(
  event: ShortcutEvent,
  apple: boolean
): ShortcutId | null {
  const primary = apple ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  if (!primary || event.altKey) return null;
  const key = event.key.toLowerCase();
  const found = SHORTCUTS.find(
    (shortcut) => shortcut.key.toLowerCase() === key && Boolean(shortcut.shift) === event.shiftKey
  );
  return found?.id ?? null;
}
