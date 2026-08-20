import { describe, expect, it } from "vitest";
import { buildChatQueryBody, errorMessage } from "./daemon";

describe("Kura chat request", () => {
  it("trims the query and selects the Loopforge router", () => {
    expect(buildChatQueryBody("  inspect this project  ")).toEqual({
      query: "inspect this project",
      skills: ["loopforge-router"]
    });
  });

  it("does not expose arbitrary thrown values", () => {
    expect(errorMessage(new Error("offline"), "failed")).toBe("offline");
    expect(errorMessage({ token: "secret" }, "failed")).toBe("failed");
  });
});
