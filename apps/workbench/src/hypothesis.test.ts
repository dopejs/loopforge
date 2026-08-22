import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { HYPOTHESIS_FIELDS, emptyFields } from "./hypothesis";

/**
 * The field list is duplicated in TypeScript because the Workbench renders a
 * form from it. That duplication is only safe while it matches the contract,
 * and a field the core added but this list lacks would silently never be
 * shown -- a hypothesis recorded as incomplete with no visible cause.
 */
describe("hypothesis fields", () => {
  const schema = JSON.parse(
    readFileSync(
      new URL("../../../contracts/loopforge-hypothesis-v1.schema.json", import.meta.url),
      "utf8"
    )
  );

  it("matches the contract exactly, in order", () => {
    expect([...HYPOTHESIS_FIELDS]).toEqual(
      Object.keys(schema.properties.fields.properties)
    );
  });

  it("starts every field empty", () => {
    const fields = emptyFields();
    expect(Object.keys(fields)).toEqual([...HYPOTHESIS_FIELDS]);
    expect(Object.values(fields).every((value) => value === "")).toBe(true);
  });
});
