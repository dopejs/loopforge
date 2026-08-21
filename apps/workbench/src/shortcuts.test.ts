import { describe, expect, it } from "vitest";
import {
  SHORTCUTS,
  type ShortcutEvent,
  displayShortcut,
  isApplePlatform,
  matchShortcut
} from "./shortcuts";

function press(overrides: Partial<ShortcutEvent> & { key: string }): ShortcutEvent {
  return { metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...overrides };
}

describe("matchShortcut", () => {
  it("matches the primary modifier on macOS", () => {
    expect(matchShortcut(press({ key: "k", metaKey: true }), true)).toBe("focusComposer");
    expect(matchShortcut(press({ key: "]", metaKey: true }), true)).toBe("nextMode");
    expect(matchShortcut(press({ key: ",", metaKey: true }), true)).toBe("settings");
  });

  it("matches Ctrl on non-Apple platforms", () => {
    expect(matchShortcut(press({ key: "k", ctrlKey: true }), false)).toBe("focusComposer");
  });

  it("does not accept the wrong platform modifier", () => {
    expect(matchShortcut(press({ key: "k", ctrlKey: true }), true)).toBeNull();
    expect(matchShortcut(press({ key: "k", metaKey: true }), false)).toBeNull();
  });

  it("ignores unmodified keys so typing in the composer is never captured", () => {
    expect(matchShortcut(press({ key: "k" }), true)).toBeNull();
    expect(matchShortcut(press({ key: "[" }), false)).toBeNull();
  });

  it("ignores Alt-modified combinations", () => {
    expect(matchShortcut(press({ key: "k", metaKey: true, altKey: true }), true)).toBeNull();
  });

  it("is case-insensitive about the reported key", () => {
    expect(matchShortcut(press({ key: "K", metaKey: true }), true)).toBe("focusComposer");
  });

  it("returns null for keys with no binding", () => {
    expect(matchShortcut(press({ key: "q", metaKey: true }), true)).toBeNull();
  });

  it("requires shift state to match exactly", () => {
    expect(matchShortcut(press({ key: "k", metaKey: true, shiftKey: true }), true)).toBeNull();
  });
});

describe("shortcut table", () => {
  it("binds each key combination only once", () => {
    const combos = SHORTCUTS.map((shortcut) => `${shortcut.key.toLowerCase()}:${Boolean(shortcut.shift)}`);
    expect(new Set(combos).size).toBe(combos.length);
  });

  it("renders the platform modifier symbol", () => {
    const focus = SHORTCUTS.find((shortcut) => shortcut.id === "focusComposer")!;
    expect(displayShortcut(focus, true)).toBe("⌘ K");
    expect(displayShortcut(focus, false)).toBe("Ctrl + K");
  });
});

describe("isApplePlatform", () => {
  it("detects Apple platforms", () => {
    expect(isApplePlatform("MacIntel")).toBe(true);
    expect(isApplePlatform("iPhone")).toBe(true);
    expect(isApplePlatform("Win32")).toBe(false);
    expect(isApplePlatform("Linux x86_64")).toBe(false);
  });
});
