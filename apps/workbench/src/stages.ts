import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * The project lifecycle as the core defines it.
 *
 * Laid out as the stage machine actually branches: a linear spine from
 * discovery to the decision, then three outcomes. The Workbench never decides
 * whether a transition is legal -- `next_stages` comes from the Agent, and
 * this table only positions what it names.
 */
export const STAGES = [
  { id: "DISCOVERY", column: 1, row: 1, arrow: "right" },
  { id: "PROTOTYPING", column: 2, row: 1, arrow: "right" },
  { id: "PLAYTEST_REQUIRED", column: 3, row: 1, arrow: "right" },
  { id: "PROTOTYPE_DECISION", column: 4, row: 1, arrow: "" },
  { id: "VERTICAL_SLICE", column: 4, row: 2, arrow: "" },
  { id: "KILLED", column: 3, row: 2, arrow: "" }
] as const;

export type StageId = (typeof STAGES)[number]["id"];

/** `missing` and `invalid` are distinct: one is unmet, the other impossible. */
export type RequirementStatus = "satisfied" | "missing" | "invalid";

export type Requirement = {
  code: string;
  status: RequirementStatus;
  /** The core's own remediation text; shown verbatim. */
  message: string;
  evidence_ids: readonly string[];
};

export type Gate = {
  schema_version: "loopforge-gate-v1";
  gate: string;
  from_stage: string;
  result: "pass" | "blocked" | string;
  requirements: readonly Requirement[];
  next_stages: readonly string[];
  observed_revision?: number;
};

export type Advance = {
  schema_version: "loopforge-gate-v1";
  from_stage: string;
  to_stage: string;
  committed_revision?: number;
};

export function requirementTone(status: string): "ok" | "bad" | "faint" {
  if (status === "satisfied") return "ok";
  if (status === "invalid") return "bad";
  return "faint";
}

/**
 * Reasons the core accepts for cutting an experiment short.
 *
 * Only the PROTOTYPING → PROTOTYPE_DECISION transition takes one, and it is
 * recorded in the event log: a later reader interprets the project's end
 * differently depending on which of these it was.
 */
export const TRANSITION_REASONS = ["technical", "scope", "abandon"] as const;

export type TransitionReason = (typeof TRANSITION_REASONS)[number];

/** Arguments some gates test directly rather than reading from the record. */
export type GateArgs = {
  reason?: string;
  approver_id?: string;
  approver_name?: string;
  rationale?: string;
};

/** Reads the gate for one target stage. */
export function useGate(projectRoot: string, stage: string | null, args?: GateArgs) {
  const [gate, setGate] = useState<Gate | null>(null);
  const [reason, setReason] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!projectRoot || !stage) {
      setGate(null);
      return;
    }
    if (!isDesktopRuntime()) {
      setReason("desktop-only");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setReason(undefined);
    void invoke<Gate>("agent_gate", {
      projectPath: projectRoot,
      stage,
      reason: args?.reason ?? null,
      approverId: args?.approver_id ?? null,
      approverName: args?.approver_name ?? null,
      rationale: args?.rationale ?? null
    })
      .then((result) => {
        if (!cancelled) setGate(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Gate unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // The arguments are part of the question, so a change to them re-asks it.
  }, [projectRoot, stage, nonce, args?.reason, args?.approver_id, args?.approver_name, args?.rationale]);

  return { gate, reason, loading, reload };
}

/**
 * Attempts a transition.
 *
 * Not pre-checked against the gate: the core decides, and a refusal carries
 * the reason. A Workbench that blocked this itself would be a second
 * implementation of the rule.
 */
export function advanceStage(
  projectRoot: string,
  stage: string,
  args?: GateArgs
): Promise<Advance> {
  return invoke<Advance>("agent_advance", {
    projectPath: projectRoot,
    stage,
    ...(args ?? {})
  });
}
