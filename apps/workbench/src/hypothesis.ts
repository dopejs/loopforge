import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-hypothesis-v1`.
 *
 * The field order is the order the core declares and the order a discovery
 * conversation moves through, so it is also the order the form renders.
 */
export const HYPOTHESIS_FIELDS = [
  "intended_player",
  "platform",
  "player_fantasy",
  "core_verb",
  "moment_to_moment_loop",
  "hypothesis",
  "constraints",
  "non_goals",
  "cheapest_validation",
  "keep_signals",
  "kill_signals"
] as const;

export type HypothesisField = (typeof HYPOTHESIS_FIELDS)[number];

export type HypothesisFields = Record<HypothesisField, string>;

export type Hypothesis = {
  schema_version: "loopforge-hypothesis-v1";
  present: boolean;
  /** True only for an unrecorded model proposal. */
  draft?: boolean;
  hypothesis_id?: string;
  revision?: number;
  fields: HypothesisFields;
  /** Field names that are still empty, from the Agent rather than recomputed. */
  missing: readonly HypothesisField[];
};

export function emptyFields(): HypothesisFields {
  return Object.fromEntries(HYPOTHESIS_FIELDS.map((key) => [key, ""])) as HypothesisFields;
}

/** Reads the active hypothesis. Absence is a normal state, not an error. */
export function useHypothesis(projectRoot: string, enabled: boolean) {
  const [hypothesis, setHypothesis] = useState<Hypothesis | null>(null);
  const [reason, setReason] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !projectRoot) return;
    if (!isDesktopRuntime()) {
      setReason("desktop-only");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setReason(undefined);
    void invoke<Hypothesis>("agent_hypothesis", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setHypothesis(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Hypothesis unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { hypothesis, reason, loading, reload };
}

/**
 * Asks the model for a draft.
 *
 * The result is a proposal and is deliberately not recorded: the user edits
 * and submits it, so an approval is attributed to something they read.
 */
export function draftHypothesis(projectRoot: string, brief: string): Promise<Hypothesis> {
  return invoke<Hypothesis>("agent_hypothesis_draft", { projectPath: projectRoot, brief });
}

/** Records reviewed fields. The Agent refuses an incomplete set. */
export function createHypothesis(
  projectRoot: string,
  fields: HypothesisFields
): Promise<Hypothesis> {
  return invoke<Hypothesis>("agent_hypothesis_create", { projectPath: projectRoot, fields });
}
