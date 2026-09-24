import { describe, expect, it } from "vitest";
import { emptyReport, serializeReport, toLines } from "./playtest";

describe("playtest report serialisation", () => {
  it("starts with consent unanswered", () => {
    // The rule the whole form is built around: either answer is a claim about
    // a real person, so neither can be a default.
    expect(emptyReport().consent_status).toBe("");
  });

  it("binds the report to the core-provided build identity", () => {
    const form = emptyReport("sha256:tested-build");
    expect(form.build_identity).toBe("sha256:tested-build");
    expect(serializeReport(form).build_identity).toBe("sha256:tested-build");
  });

  it("splits list fields on lines and drops blanks", () => {
    expect(toLines("first\n\n  second  \n   \nthird")).toEqual([
      "first",
      "second",
      "third"
    ]);
  });

  it("keeps observations and interpretation as distinct fields", () => {
    const payload = serializeReport({
      ...emptyReport(),
      consent_status: "obtained",
      assistance_given: "None.",
      raw_observations: "charged twice\ndied once",
      interpretation: "the trade-off reads",
      sensitive_data: "No identifying data collected."
    });

    expect(payload.raw_observations).toEqual(["charged twice", "died once"]);
    expect(payload.interpretation).toBe("the trade-off reads");
    expect(payload.assistance_given).toBe("None.");
    expect(payload.sensitive_data).toBe("No identifying data collected.");
    // Structural separation, not a formatting choice: a later reader has to be
    // able to tell what was seen from what was concluded.
    expect(payload.raw_observations).not.toContain("the trade-off reads");
  });

  it("sends empty optional lists rather than omitting them", () => {
    const payload = serializeReport({ ...emptyReport(), consent_status: "obtained" });
    // The core requires the keys to exist; omitting them fails validation with
    // a less useful message than the Agent's own.
    for (const field of ["confusion_points", "failure_points", "abandonment_points", "strategies"]) {
      expect(payload[field]).toEqual([]);
    }
  });

  it("passes an unanswered consent through so the Agent refuses it", () => {
    // Not corrected here. The Workbench must not invent an answer, and the
    // refusal has to come from the layer that owns the rule.
    expect(serializeReport(emptyReport()).consent_status).toBe("");
  });
});
