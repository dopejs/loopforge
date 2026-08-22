import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-run-v1`. Engine runs are written by the deterministic
 * core (`LoopforgeProject.run_engine`) and read back through the Agent; the
 * Terminal and Test workspaces are two views of this one source.
 */
export type RunStatus = "completed" | "failed" | "interrupted" | "unknown";

export type Run = {
  id: string;
  operation: string;
  adapter: string;
  adapter_version: string;
  status: RunStatus;
  /** Absent when the process did not exit normally. */
  exit_code: number | null;
  timed_out: boolean;
  started_at: string;
  finished_at: string;
};

export type RunDetail = Run & {
  stdout: string;
  stderr: string;
  command: readonly string[];
};

export type RunState = {
  runs: readonly Run[];
  reason?: string;
  loading: boolean;
  reload: () => void;
};

/** Reads engine run history, optionally narrowed to one operation. */
export function useRuns(
  projectRoot: string,
  enabled: boolean,
  operation?: "build" | "test"
): RunState {
  const [runs, setRuns] = useState<readonly Run[]>([]);
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
    void invoke<{ runs: Run[] }>("agent_runs", { projectPath: projectRoot, operation })
      .then((result) => {
        if (!cancelled) setRuns(result.runs ?? []);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Run history unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, nonce, operation, projectRoot]);

  return { runs, reason, loading, reload };
}

/** Reads one run's captured output, lazily. */
export function useRunDetail(projectRoot: string, runId: string | null): RunDetail | null {
  const [detail, setDetail] = useState<RunDetail | null>(null);

  useEffect(() => {
    if (!runId || !projectRoot || !isDesktopRuntime()) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void invoke<{ run: RunDetail }>("agent_run", { projectPath: projectRoot, runId })
      .then((result) => {
        if (!cancelled) setDetail(result.run);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectRoot, runId]);

  return detail;
}

/** A run's outcome as a display tone. */
export function runTone(run: Run): "ok" | "bad" | "faint" {
  if (run.status === "completed") return "ok";
  if (run.status === "failed" || run.timed_out) return "bad";
  return "faint";
}
