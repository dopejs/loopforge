import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-evidence-v1`.
 *
 * `trust_level` is carried rather than flattened away: `tool_generated`
 * evidence came from a run, `manually_imported` from a person choosing a file.
 * A decision cites both, and a reader has to be able to tell them apart.
 */
export type TrustLevel = "tool_generated" | "manually_imported" | "human_attested";

export type Evidence = {
  id: string;
  type: string;
  result: string;
  trust_level: TrustLevel | string;
  producer: string;
  created_at: string;
  path: string;
  /** `absolute` means the file lives outside the project and is only linked. */
  path_kind: "project-relative" | "absolute" | string;
};

export function evidenceTone(result: string): "ok" | "bad" | "faint" {
  if (result === "passed") return "ok";
  if (result === "failed") return "bad";
  return "faint";
}

export function useEvidence(projectRoot: string, enabled: boolean) {
  const [evidence, setEvidence] = useState<readonly Evidence[]>([]);
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
    void invoke<{ evidence: Evidence[] }>("agent_evidence", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setEvidence(result.evidence ?? []);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Evidence unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { evidence, reason, loading, reload };
}

/** Opens the native picker. Resolves to null when the user cancels. */
export function chooseCaptureFile(): Promise<string | null> {
  return invoke<string | null>("select_capture_file");
}

/**
 * Registers an existing screenshot.
 *
 * Nothing is captured and nothing is copied: the core records the path and a
 * checksum. A file outside the project is referenced, so moving it later
 * breaks the link.
 */
export function registerCapture(
  projectRoot: string,
  path: string
): Promise<{ evidence: Evidence }> {
  return invoke<{ evidence: Evidence }>("agent_capture", { projectPath: projectRoot, path });
}
