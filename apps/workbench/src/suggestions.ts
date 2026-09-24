import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useI18n } from "./i18n";
import { isDesktopRuntime } from "./agent";
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
 * Fixed rather than generated, and the reason is the failure mode rather than
 * the quality. A model can suggest better than this list can -- it can name the
 * hypothesis you actually wrote -- but asking it at the moment the chat opens
 * costs a round trip before the person has said anything, and fails outright on
 * a fresh install where no provider is configured yet. That is exactly when
 * someone most needs to be told how to start. So this is the floor: instant,
 * and available with nothing else working. Grounded suggestions belong at the
 * end of a turn, where the model has already read the state and costs nothing
 * extra to ask.
 */
export type Suggestion = {
  /** The prompt sent when it is clicked, in the reader's language. */
  key: MessageKey;
};

/**
 * Keyed by stage.
 *
 * No stage mentions Loopforge's own record-keeping, `UNINITIALIZED` least of
 * all. It used to offer "set this folder up so we can start working on a game",
 * on the reasoning that an unset-up folder makes setting up the honest answer.
 * That reasoning was backwards: nobody opens this wanting a folder prepared,
 * they open it wanting to make a game, and the first thing we taught them to
 * say was our own bookkeeping. Setting up is a consequence of asking for work
 * -- the agent does it when it needs it, behind the same approval as any other
 * change -- so the suggestions here are the three ways a person actually
 * arrives: with an idea, without one, or not knowing how this goes.
 */
const BY_STAGE: Record<string, readonly MessageKey[]> = {
  UNINITIALIZED: [
    "suggest.haveAnIdea",
    "suggest.noIdeaYet",
    "suggest.howThisWorks"
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

/**
 * The generated set, layered over the fixed one.
 *
 * The fixed list renders immediately and is never wrong, only generic. The
 * Agent writes a better one -- grounded in this project, in the reader's
 * language -- at the end of a turn and when a conversation is opened, and this
 * swaps it in when it arrives.
 *
 * Never a spinner and never a gap. A person opening an empty chat has
 * something to click in the first frame; if the generated set is late, or the
 * model is not configured at all, they keep the generic one and lose nothing.
 */
export type GeneratedSuggestions = {
  schema_version: "loopforge-suggestion-v1";
  suggestions: readonly string[];
  stage?: string;
  /** Whether one is actually being written -- not merely whether one is missing. */
  generating: boolean;
};

/**
 * How often to look while one is being written.
 *
 * Only while `generating` says somebody is writing one, so a project whose
 * suggestions are current, or whose runtime is down, is not polled at all.
 */
const POLL_INTERVAL_MS = 3000;

export function useSuggestions(
  projectRoot: string,
  locale: string,
  stage: string | undefined,
  enabled: boolean
): readonly string[] {
  const { t } = useI18n();
  const [generated, setGenerated] = useState<readonly string[]>([]);

  useEffect(() => {
    setGenerated([]);
    if (!enabled || !projectRoot || !isDesktopRuntime()) return;
    let cancelled = false;
    let timer: number | undefined;

    const read = async (): Promise<void> => {
      try {
        const answer = await invoke<GeneratedSuggestions>("agent_suggestions", {
          projectPath: projectRoot,
          locale
        });
        if (cancelled) return;
        const items = answer.suggestions ?? [];
        setGenerated(items);
        // Stop as soon as there is nothing more coming. Polling a runtime that
        // is not writing one would ask forever for an answer nobody is
        // preparing.
        if (items.length === 0 && answer.generating) {
          timer = window.setTimeout(() => void read(), POLL_INTERVAL_MS);
        }
      } catch {
        // The Agent may simply not be up. The fixed list is behind this, so
        // there is nothing to report and nothing to retry.
      }
    };

    void read();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled, projectRoot, locale, stage]);

  // Translated keys are resolved here so a caller renders one list of strings
  // and does not have to know which of them came from a model.
  return generated.length > 0 ? generated : suggestionsFor(stage).map((key) => t(key));
}
