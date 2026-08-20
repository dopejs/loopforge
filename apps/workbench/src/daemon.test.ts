import { describe, expect, it } from "vitest";
import { errorMessage } from "./daemon";

describe("Loopforge Agent client", () => {
  it("does not expose arbitrary thrown values", () => {
    expect(errorMessage(new Error("offline"), "failed")).toBe("offline");
    expect(errorMessage({ token: "secret" }, "failed")).toBe("failed");
  });
});
