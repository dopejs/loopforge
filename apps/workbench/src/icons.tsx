import React from "react";
import type { Mode } from "./modes";

/**
 * Icon geometry is taken from the Workbench design. Every glyph is decorative:
 * the interactive element that wraps it carries the accessible name.
 */
const GLYPHS: Record<Mode | "chevron" | "check" | "folder" | "search" | "plus", React.ReactNode> = {
  canvas: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M3 10h18M10 10v10" />
    </>
  ),
  flow: (
    <>
      <circle cx="6" cy="6" r="2.4" />
      <circle cx="18" cy="12" r="2.4" />
      <circle cx="6" cy="18" r="2.4" />
      <path d="M8.3 7.3l7.4 3.6M8.3 16.7l7.4-3.6" />
    </>
  ),
  test: <path d="M4 12.8l4.8 4.7L20 6.4" />,
  chat: <path d="M4 7a2 2 0 012-2h12a2 2 0 012 2v7a2 2 0 01-2 2H9.5L4.5 20V7z" />,
  diff: <path d="M7 19V6M7 6L4.2 8.8M7 6l2.8 2.8M17 5v13M17 18l2.8-2.8M17 18l-2.8-2.8" />,
  terminal: (
    <>
      <rect x="3.5" y="5" width="17" height="14" rx="2.5" />
      <path d="M7 10.5l2.4 2.2L7 14.9M12.6 15.4h4" />
    </>
  ),
  tasks: (
    <>
      <rect x="4" y="4.5" width="6.5" height="15" rx="1.6" />
      <rect x="13.5" y="4.5" width="6.5" height="9" rx="1.6" />
    </>
  ),
  assets: (
    <>
      <rect x="3.5" y="5" width="17" height="14" rx="2.5" />
      <path d="M3.5 15.5l4.6-4.4 4 3.9 2.9-2.8 4.5 4.3" />
    </>
  ),
  profiler: <path d="M4.5 19V10M9.8 19V5.5M15.2 19v-5.5M20.5 19v-9" />,
  settings: (
    <>
      <path d="M4 7.5h5.5M14.5 7.5H20M4 16.5h9.5M18.5 16.5H20" />
      <circle cx="12" cy="7.5" r="2.4" />
      <circle cx="16" cy="16.5" r="2.4" />
    </>
  ),
  chevron: <path d="m6 9 6 6 6-6" />,
  check: <path d="m4 12.5 5 5L20 6.5" />,
  folder: <path d="M3 7.5A1.5 1.5 0 014.5 6h4l2 2.5h7A1.5 1.5 0 0119 10v7.5A1.5 1.5 0 0117.5 19h-13A1.5 1.5 0 013 17.5z" />,
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="M15 15l4 4" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />
};

export type IconName = keyof typeof GLYPHS;

export function Icon({ name, size = 17 }: { name: IconName; size?: number }): React.JSX.Element {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {GLYPHS[name]}
    </svg>
  );
}
