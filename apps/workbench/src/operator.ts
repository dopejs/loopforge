import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Who is approving.
 *
 * Loopforge is a local agent with no cross-user collaboration, so there is no
 * role model here: the approver is whoever is using the Workbench. The core
 * reflects that by stamping every approval `identity_source:
 * "local-declaration"` -- it does not claim the identity was verified.
 *
 * Held by the Agent rather than in this window's local storage. It used to be
 * the latter, which meant the Agent could not read it and every approval had
 * to carry one in from the front end; anything that was not the Workbench had
 * no identity at all. Surfaces now record approvals without naming anyone, and
 * the Agent fills in the operator it has stored.
 */
export type Operator = {
  schema_version: "loopforge-settings-v1";
  /** Stable across renames, so a history of approvals stays one person. */
  id: string;
  name: string;
  /** A name is what makes an approval readable later; without one, false. */
  configured: boolean;
  reason?: string;
};

export function useOperator(projectRoot: string, enabled: boolean) {
  const [operator, setOperator] = useState<Operator | null>(null);
  const [reason, setReason] = useState<string>();
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !projectRoot || !isDesktopRuntime()) return;
    let cancelled = false;
    void invoke<Operator>("agent_operator_settings", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setOperator(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Operator unavailable"));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { operator, reason, reload };
}

/** Records the name. The Agent mints the id on first use and keeps it. */
export function saveOperator(projectRoot: string, name: string): Promise<Operator> {
  return invoke<Operator>("agent_save_operator_settings", {
    projectPath: projectRoot,
    name
  });
}

/** An approval is only recorded for someone who has been named. */
export function isConfigured(operator: Operator | null): boolean {
  return operator?.configured === true;
}
