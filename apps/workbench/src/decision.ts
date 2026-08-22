import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";
import type { HypothesisFields } from "./hypothesis";

/**
 * Mirrors `loopforge-decision-v1`.
 *
 * The outcome list comes from the Agent rather than being spelled here. Three
 * equal options is the product's position, and hard-coding an order in the UI
 * is how a default quietly appears.
 */
export type DecisionOutcome = "keep" | "kill" | "refactor";

export type DecisionState = {
  schema_version: "loopforge-decision-v1";
  stage: string;
  /** Only PROTOTYPE_DECISION allows this. */
  allowed: boolean;
  decisions: readonly string[];
  /**
   * The core requires a `keep` to cite the applicable playtest, not merely for
   * one to exist, so a surface can warn before the refusal.
   */
  playtest_evidence_ids: readonly string[];
  recorded: { decision: string; created_at: string } | null;
};

export type DecisionResult = {
  schema_version: "loopforge-decision-v1";
  decision: string;
  stage: string;
  committed_revision?: number;
};

/** Where each outcome leaves the project, for showing before it is chosen. */
export const DECISION_TARGET: Record<string, string> = {
  keep: "VERTICAL_SLICE",
  kill: "KILLED",
  refactor: "PROTOTYPING"
};

export function useDecision(projectRoot: string, enabled: boolean) {
  const [decision, setDecision] = useState<DecisionState | null>(null);
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
    void invoke<DecisionState>("agent_decision", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setDecision(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Decision state unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { decision, reason, loading, reload };
}

/**
 * Records the decision.
 *
 * Evidence and rationale are mandatory in the core and are not filled in here:
 * a decision recorded without them would be a claim with nothing behind it.
 * The approver comes from the operator the Agent stores.
 */
export function recordDecision(
  projectRoot: string,
  input: {
    decision: string;
    evidenceIds: readonly string[];
    rationale: string;
    revisedFields?: HypothesisFields;
  }
): Promise<DecisionResult> {
  return invoke<DecisionResult>("agent_decide", {
    projectPath: projectRoot,
    decision: input.decision,
    evidenceIds: input.evidenceIds,
    rationale: input.rationale,
    revisedFields: input.revisedFields ?? null
  });
}
