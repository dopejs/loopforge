import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-project-health-v1` and `loopforge-history-v1`.
 *
 * ADR 0003 treats interrupted writes and stale snapshots as normal conditions.
 * `needs_reconcile` is its own field rather than one diagnostic among many,
 * because it is the single condition that blocks every gate and the only one
 * the user can clear from here.
 */
export type Diagnostic = {
  code: string;
  severity: "error" | "warning" | string;
  message: string;
};

export type Check = {
  code: string;
  status: "passed" | "failed" | "warning" | string;
  message: string;
};

export type ProjectHealth = {
  schema_version: "loopforge-project-health-v1";
  initialized: boolean;
  valid: boolean;
  snapshot_status: string;
  needs_reconcile: boolean;
  event_count?: number;
  observed_revision?: number;
  diagnostics: readonly Diagnostic[];
  checks: readonly Check[];
};

export type ReconcileAction = {
  action: string;
  from_status: string;
  target_revision?: number;
};

export type ReconcileResult = {
  schema_version: "loopforge-project-health-v1";
  applied: boolean;
  actions: readonly ReconcileAction[];
  snapshot_status: string;
  observed_revision?: number;
};

export type HistoryEvent = {
  revision?: number;
  event_type: string;
  occurred_at: string;
  /** A short human-readable summary; payloads are not carried. */
  detail: string;
};

export type History = {
  schema_version: "loopforge-history-v1";
  events: readonly HistoryEvent[];
  /** Stated rather than silently cut: a partial trail must not read as whole. */
  truncated: boolean;
};

export function checkTone(status: string): "ok" | "bad" | "accent" | "faint" {
  if (status === "passed") return "ok";
  if (status === "failed") return "bad";
  if (status === "warning") return "accent";
  return "faint";
}

export function useProjectHealth(projectRoot: string, enabled: boolean) {
  const [health, setHealth] = useState<ProjectHealth | null>(null);
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
    void invoke<ProjectHealth>("agent_project_health", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setHealth(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Project health unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { health, reason, loading, reload };
}

export function useHistory(projectRoot: string, enabled: boolean) {
  const [history, setHistory] = useState<History | null>(null);
  const [reason, setReason] = useState<string>();

  useEffect(() => {
    if (!enabled || !projectRoot || !isDesktopRuntime()) return;
    let cancelled = false;
    void invoke<History>("agent_project_history", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setHistory(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "History unavailable"));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot]);

  return { history, reason };
}

/**
 * Rebuilds the derived state snapshot from the event log.
 *
 * `apply: false` previews the work and changes nothing. The caller is expected
 * to preview first and show the result, because this rewrites derived state
 * and must never happen without the user seeing what it would do.
 */
export function reconcileProject(
  projectRoot: string,
  apply: boolean
): Promise<ReconcileResult> {
  return invoke<ReconcileResult>("agent_project_reconcile", {
    projectPath: projectRoot,
    apply
  });
}
