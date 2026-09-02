import { describe, expect, it } from "vitest";
import { en } from "./i18n/locales/en";
import { suggestionsFor } from "./suggestions";
import { STAGES } from "./stages";

/**
 * What an empty chat offers.
 *
 * "How can I help?" leaves a person to guess, so they type something vague, and
 * the agent answers by reporting project state and offering to initialize. That
 * is us teaching them that the way to use this is to ask for our bookkeeping.
 */
describe("suggestionsFor", () => {
  it("offers something at every stage the project can be in", () => {
    // A stage with nothing to suggest is an empty chat again, at exactly the
    // moment someone has arrived and does not know what to do.
    for (const stage of STAGES) {
      expect(suggestionsFor(stage.id).length, stage.id).toBeGreaterThan(0);
    }
  });

  it("offers the one answerable question when the stage is unknown", () => {
    // The status may not have been read yet. Guessing a richer set would
    // suggest work the project is not ready for, and being told to do
    // something the core then refuses is worse than being told less.
    expect(suggestionsFor(undefined)).toEqual(["suggest.whereAmI"]);
    expect(suggestionsFor("SOMETHING_NEW")).toEqual(["suggest.whereAmI"]);
  });

  it("says every suggestion in the reader's language", () => {
    // These are sent verbatim as the person's own message. A missing key would
    // send the key.
    const catalogue = en as Record<string, string>;
    for (const stage of [...STAGES.map((s) => s.id), undefined]) {
      for (const key of suggestionsFor(stage)) {
        expect(catalogue[key], `${stage}: ${key}`).toBeTruthy();
      }
    }
  });

  it("asks for work rather than for record-keeping", () => {
    // Except where the project genuinely is not set up, a suggestion should
    // never teach someone Loopforge's vocabulary. Nobody arrives wanting to
    // advance a stage; they want to know if the game is any good.
    const catalogue = en as Record<string, string>;
    //  starts at DISCOVERY: an uninitialized folder has no stage, and
    // there setting the project up genuinely is the honest suggestion.
    for (const stage of STAGES.map((s) => s.id)) {
      for (const key of suggestionsFor(stage)) {
        const text = catalogue[key].toLowerCase();
        expect(text, key).not.toContain("loopforge");
        expect(text, key).not.toContain("revision");
        expect(text, key).not.toContain("gate");
      }
    }
  });
});
