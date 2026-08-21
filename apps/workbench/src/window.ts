import type React from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";

/**
 * The window uses an overlay title bar, so the chrome has to provide its own
 * drag surfaces. Clicks that land on a control are left alone, and in the
 * browser-only dev shell there is no window to drag.
 */
export function startWindowDrag(event: React.MouseEvent<HTMLElement>): void {
  if (
    event.button !== 0 ||
    (event.target as HTMLElement).closest("button, input, textarea, select, a, [role='button']")
  ) {
    return;
  }
  if (!("__TAURI_INTERNALS__" in window)) return;
  void getCurrentWindow()
    .startDragging()
    .catch((error: unknown) => {
      console.error("Failed to start native window dragging", error);
    });
}
