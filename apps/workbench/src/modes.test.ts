import { describe, expect, it } from "vitest";
import { WORKSPACE_MODES, isWired, isWorkspaceMode, stepMode } from "./modes";

describe("stepMode", () => {
  it("advances and wraps forwards", () => {
    expect(stepMode("canvas", 1)).toBe("flow");
    expect(stepMode("profiler", 1)).toBe("canvas");
  });

  it("advances and wraps backwards", () => {
    expect(stepMode("flow", -1)).toBe("canvas");
    expect(stepMode("canvas", -1)).toBe("profiler");
  });

  it("treats settings as outside the workspace ring and starts from the first mode", () => {
    expect(stepMode("settings", 1)).toBe("flow");
    expect(stepMode("settings", -1)).toBe("profiler");
  });

  it("stays inside the ring for any delta", () => {
    for (const delta of [-13, -1, 0, 1, 25]) {
      expect(WORKSPACE_MODES).toContain(stepMode("test", delta));
    }
  });
});

describe("mode classification", () => {
  it("marks only agent-backed workspaces as wired", () => {
    // Chat streams from the runtime; Terminal and Test read engine run history
    // written by the deterministic core.
    const wired = ["chat", "terminal", "test"];
    for (const mode of wired) {
      expect(isWired(mode as (typeof WORKSPACE_MODES)[number]), mode).toBe(true);
    }
    for (const mode of WORKSPACE_MODES.filter((m) => !wired.includes(m))) {
      expect(isWired(mode), mode).toBe(false);
    }
  });

  it("separates settings from the workspaces", () => {
    expect(isWorkspaceMode("settings")).toBe(false);
    expect(isWorkspaceMode("canvas")).toBe(true);
  });
});
