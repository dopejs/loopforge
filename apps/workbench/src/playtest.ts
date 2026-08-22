import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-playtest-v1`.
 *
 * Consent values come from the Agent rather than being spelled here, because
 * there is no third option and no default: an unanswered consent question has
 * to stay unanswered until a person answers it.
 */
export type ConsentStatus = "obtained" | "not_required";

export type PlaytestState = {
  schema_version: "loopforge-playtest-v1";
  stage: string;
  /** Both steps are legal only in PLAYTEST_REQUIRED. */
  allowed: boolean;
  protocol: { protocol_id: string; created_at: string } | null;
  consent_values: readonly string[];
  fields: readonly string[];
  list_fields: readonly string[];
};

/** Free-text fields; the rest of the report is lists. */
export const PLAYTEST_TEXT_FIELDS = [
  "participant_context",
  "comprehension_time",
  "replay_behavior"
] as const;

/** Lists the core accepts. `raw_observations` must not be empty. */
export const PLAYTEST_LIST_FIELDS = [
  "raw_observations",
  "confusion_points",
  "failure_points",
  "abandonment_points",
  "strategies"
] as const;

export type PlaytestReport = {
  participant_context: string;
  consent_status: ConsentStatus | "";
  raw_observations: string;
  comprehension_time: string;
  confusion_points: string;
  failure_points: string;
  abandonment_points: string;
  strategies: string;
  replay_behavior: string;
  interpretation: string;
};

export function emptyReport(): PlaytestReport {
  return {
    participant_context: "",
    // Deliberately empty. Pre-selecting either value would record a claim
    // about a real person that nobody made.
    consent_status: "",
    raw_observations: "",
    comprehension_time: "",
    confusion_points: "",
    failure_points: "",
    abandonment_points: "",
    strategies: "",
    replay_behavior: "",
    interpretation: ""
  };
}

/** One item per line, which is how these are actually written down. */
export function toLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Shapes the form for the Agent, which validates it again before the core. */
export function serializeReport(form: PlaytestReport): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    consent_status: form.consent_status,
    interpretation: form.interpretation,
    participant_context: form.participant_context,
    comprehension_time: form.comprehension_time,
    replay_behavior: form.replay_behavior
  };
  for (const field of PLAYTEST_LIST_FIELDS) {
    payload[field] = toLines(form[field]);
  }
  return payload;
}

export function usePlaytest(projectRoot: string, enabled: boolean) {
  const [playtest, setPlaytest] = useState<PlaytestState | null>(null);
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
    void invoke<PlaytestState>("agent_playtest", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setPlaytest(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Playtest state unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { playtest, reason, loading, reload };
}

export function draftProtocol(projectRoot: string): Promise<{ content: string }> {
  return invoke<{ content: string }>("agent_playtest_draft", { projectPath: projectRoot });
}

export function saveProtocol(projectRoot: string, content: string): Promise<PlaytestState> {
  return invoke<PlaytestState>("agent_playtest_protocol", {
    projectPath: projectRoot,
    content
  });
}

export function importReport(
  projectRoot: string,
  report: Record<string, unknown>
): Promise<PlaytestState> {
  return invoke<PlaytestState>("agent_playtest_report", { projectPath: projectRoot, report });
}
