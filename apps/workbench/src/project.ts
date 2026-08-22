import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-project-status-v1`.
 *
 * Claims are orthogonal derived results, not a completion percentage: a
 * passing build must never read as a validated game (ADR 0002).
 */
export type ClaimName =
  | "TECHNICALLY_VALIDATED"
  | "VISUALLY_REVIEWED"
  | "HUMAN_PLAYTESTED"
  | "FUN_HYPOTHESIS_SUPPORTED"
  | "RELEASE_APPROVED";

/** `stale` means evidence exists but no longer matches the current source. */
export type ClaimStatus = "satisfied" | "failed" | "stale" | "unknown";

export type Claim = {
  claim: ClaimName;
  status: ClaimStatus;
  evidence_count: number;
};

export type ProjectStatus = {
  schema_version: "loopforge-project-status-v1";
  initialized: boolean;
  stage?: string;
  observed_revision?: number;
  evidence_count?: number;
  snapshot_status?: string;
  experiment?: {
    experiment_id?: string;
    hypothesis_id?: string | null;
    hypothesis_revision?: number | null;
    hypothesis_approval?: string | null;
  };
  claims?: readonly Claim[];
  reason?: string;
};

/** Result of creating project state; `created` is false when one existed. */
export type ProjectInit = {
  schema_version: "loopforge-project-status-v1";
  created: boolean;
  project_root: string;
  stage: string;
};

/**
 * Creates Loopforge state in a directory.
 *
 * Idempotent in the core, so this adopts an existing project rather than
 * failing. Callers reload status afterwards rather than trusting the returned
 * stage, since the core derives more than this response carries.
 */
export function initializeProject(projectRoot: string): Promise<ProjectInit> {
  return invoke<ProjectInit>("agent_project_init", { projectPath: projectRoot });
}

export function useProjectStatus(projectRoot: string, enabled: boolean) {
  const [status, setStatus] = useState<ProjectStatus | null>(null);
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
    void invoke<ProjectStatus>("agent_project_status", { projectPath: projectRoot })
      .then((result) => {
        if (cancelled) return;
        setStatus(result);
        setReason(result.reason);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Project status unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { status, reason, loading, reload };
}

/** Display tone for a claim. `stale` is warned about, never shown as met. */
export function claimTone(status: ClaimStatus): "ok" | "bad" | "accent" | "faint" {
  if (status === "satisfied") return "ok";
  if (status === "failed") return "bad";
  if (status === "stale") return "accent";
  return "faint";
}
