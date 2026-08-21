import { describe, expect, it } from "vitest";
import { type AgentState, agentPhase } from "./agent";

function state(ready: boolean, reason?: string): AgentState {
  return { schema_version: "loopforge-agent-status-v1", ready, reason };
}

describe("agentPhase", () => {
  it("reports unsupported outside the desktop shell, whatever else is true", () => {
    expect(agentPhase("/tmp/game", false, state(true), false)).toBe("unsupported");
    expect(agentPhase("", true, state(false), false)).toBe("unsupported");
  });

  it("reports no project before one is selected, whatever the agent says", () => {
    expect(agentPhase("", false, state(true), true)).toBe("no-project");
    expect(agentPhase("", true, state(false), true)).toBe("no-project");
  });

  it("reports starting while the lifecycle is in flight", () => {
    expect(agentPhase("/tmp/game", true, state(false), true)).toBe("starting");
  });

  it("prefers starting over a stale ready status", () => {
    expect(agentPhase("/tmp/game", true, state(true), true)).toBe("starting");
  });

  it("reports ready and offline from the agent status", () => {
    expect(agentPhase("/tmp/game", false, state(true), true)).toBe("ready");
    expect(agentPhase("/tmp/game", false, state(false, "boom"), true)).toBe("offline");
  });
});
