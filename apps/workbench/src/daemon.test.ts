import { describe, expect, it } from "vitest";
import { ensureAgentReady, errorMessage } from "./daemon";

describe("Loopforge Agent client", () => {
  it("does not expose arbitrary thrown values", () => {
    expect(errorMessage(new Error("offline"), "failed")).toBe("offline");
    expect(errorMessage({ token: "secret" }, "failed")).toBe("failed");
  });

  it("starts an unavailable Agent without requiring user lifecycle controls", async () => {
    const calls: string[] = [];
    const result = await ensureAgentReady(async (command) => {
      calls.push(command);
      return { ready: command === "agent_start" };
    });

    expect(result.ready).toBe(true);
    expect(calls).toEqual(["agent_status", "agent_start"]);
  });

  it("reuses an Agent that is already ready", async () => {
    const calls: string[] = [];
    await ensureAgentReady(async (command) => {
      calls.push(command);
      return { ready: true };
    });

    expect(calls).toEqual(["agent_status"]);
  });
});
