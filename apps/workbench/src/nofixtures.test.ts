import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Nothing outside a preview workspace may render made-up data.
 *
 * The workspaces that are still mock-ups say so with a banner. Everywhere else
 * the rule is that a surface shows what the Agent reported or shows nothing --
 * and the failures that made this worth pinning were not subtle ones. A
 * fabricated provider, token count and dollar figure sat in the sidebar
 * directly beneath the real Agent status; an invented plan and a set of tool
 * calls filled the Agent panel before any run existed. Both read as real,
 * because everything around them was.
 *
 * A file-level rule rather than a rendering test: the point is that the
 * fixtures are not reachable from these components at all, which no amount of
 * asserting on one rendered state can establish.
 */

/** Components allowed to draw from the fixture file. */
const PREVIEW_SURFACES = new Set(["workspaces"]);

function sourceFiles(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (PREVIEW_SURFACES.has(entry.name)) continue;
      found.push(...sourceFiles(path));
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      found.push(path);
    }
  }
  return found;
}

describe("fixtures", () => {
  it("are not imported by anything outside the preview workspaces", () => {
    const offenders = sourceFiles(join(__dirname, "components"))
      .filter((path) => /from "\.\.?\/fixtures"/.test(readFileSync(path, "utf8")))
      .map((path) => path.slice(path.lastIndexOf("/") + 1));

    // Sidebar drew a fabricated provider, token count and cost directly
    // beneath the live Agent status; it still reads the sidebar's own section
    // list from here, which is layout rather than data.
    expect(offenders.filter((name) => name !== "Sidebar.tsx")).toEqual([]);
  });

  it("no longer carry a session usage figure nobody measures", () => {
    const source = readFileSync(join(__dirname, "fixtures.ts"), "utf8");

    // There is no token or cost accounting anywhere in this product yet, so
    // any figure of that shape is invented by definition.
    expect(source).not.toMatch(/SESSION_USAGE/);
    expect(source).not.toMatch(/tokens ·/);
  });

  it("no longer carry an agent plan or tool calls", () => {
    const source = readFileSync(join(__dirname, "fixtures.ts"), "utf8");

    expect(source).not.toMatch(/AGENT_PLAN/);
    expect(source).not.toMatch(/AGENT_TOOL_CALLS/);
    expect(source).not.toMatch(/PREVIEW_PROJECT/);
  });
});
