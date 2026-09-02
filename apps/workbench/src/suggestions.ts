import type { MessageKey } from "./i18n/locales/en";

/**
 * What is worth asking, where the project actually is.
 *
 * An empty chat that says "how can I help?" tells a person nothing, so they
 * type something vague, and the agent answers by reporting project state and
 * offering to set it up. That is us leading the user to ask for bookkeeping:
 * they came to make a game, and the first thing they were taught to say was
 * `initialize the project`.
 *
 * These are the questions the stage makes worth asking. Written as things a
 * person would actually want, not as commands -- "what do I need before I can
 * prototype" rather than "run the discovery gate".
 *
 * Deliberately fixed rather than generated. Asking a model what to suggest
 * costs a round trip before the person has said anything, and a suggestion
 * that changes every time you open the app is not a suggestion, it is noise.
 */
export type Suggestion = {
  /** The prompt sent when it is clicked, in the reader's language. */
  key: MessageKey;
};

/**
 * Keyed by stage.
 *
 * `UNINITIALIZED` gets one about setting the project up, because there it is
 * the honest answer. Every other stage gets questions about the work, and none
 * of them mention Loopforge's own record-keeping -- a person should never have
 * to learn our vocabulary to ask for what they want.
 */
const BY_STAGE: Record<string, readonly MessageKey[]> = {
  UNINITIALIZED: [
    "suggest.whatIsThis",
    "suggest.setUp",
    "suggest.inspectFolder"
  ],
  DISCOVERY: [
    "suggest.frameHypothesis",
    "suggest.whatBeforePrototype",
    "suggest.whereAmI"
  ],
  PROTOTYPING: [
    "suggest.buildIt",
    "suggest.whatBeforePlaytest",
    "suggest.whereAmI"
  ],
  PLAYTEST_REQUIRED: [
    "suggest.planPlaytest",
    "suggest.whatToWatch",
    "suggest.whereAmI"
  ],
  PROTOTYPE_DECISION: [
    "suggest.whatEvidenceSays",
    "suggest.whereAmI"
  ],
  VERTICAL_SLICE: [
    "suggest.approvedScope",
    "suggest.whereAmI"
  ],
  KILLED: ["suggest.whyKilled", "suggest.whereAmI"]
};

/**
 * What to offer, for a stage the app may not have read yet.
 *
 * An unknown stage gets the one question that is answerable anywhere. Guessing
 * a richer set would suggest work the project may not be ready for, and being
 * told to do something the core then refuses is worse than being told less.
 */
export function suggestionsFor(stage: string | undefined): readonly MessageKey[] {
  if (!stage) return ["suggest.whereAmI"];
  return BY_STAGE[stage] ?? ["suggest.whereAmI"];
}
