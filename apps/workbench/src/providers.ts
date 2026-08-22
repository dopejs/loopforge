import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `contracts/loopforge-provider-v1.schema.json`.
 *
 * Providers, credentials and model routing are Kura runtime capabilities. The
 * Workbench only renders what the Agent projects, and holds no provider state
 * of its own — so this is deliberately read-only.
 */
export type ProviderHealth = "ready" | "unconfigured" | "error";

export type ProviderModel = {
  id: string;
  display_name: string;
  available: boolean;
  is_default?: boolean;
  capabilities: readonly string[];
};

export type Provider = {
  id: string;
  title: string;
  family: string;
  source?: string;
  auth_mode?: string;
  health: ProviderHealth;
  ready: boolean;
  configured?: boolean;
  is_default?: boolean;
  base_url?: string;
  secret_configured?: boolean;
  account_label?: string;
  plan?: string;
  auth_status?: string;
  timeout_ms?: number;
  max_retries?: number;
  default_model?: string;
  capabilities: readonly string[];
  issues?: readonly string[];
  models: readonly ProviderModel[];
};

/** Mirrors the `role` definition in the contract. */
export type ModelRoleName = "primary" | "vision" | "image" | "video" | "embed";

export type ModelRole = {
  role: ModelRoleName;
  provider_id: string;
  model: string;
  /** False means the capability is unavailable — never fall back to a default. */
  routed: boolean;
  source: "store" | "config" | "unrouted";
};

export type ProviderInventory = {
  schema_version: "loopforge-provider-v1";
  providers: readonly Provider[];
  /**
   * Absent when the runtime exposes no role routing, which is different from
   * an empty array (routing exists, nothing routed). The UI must not show
   * "nothing routed" for a runtime that simply cannot route.
   */
  roles?: readonly ModelRole[];
  reason?: string;
};

export type Session = {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
};

export type SessionInventory = {
  schema_version: "loopforge-session-v1";
  sessions: readonly Session[];
  reason?: string;
};

export type ProviderState = {
  providers: readonly Provider[];
  roles?: readonly ModelRole[];
  /** Why the inventory is empty, when it is. */
  reason?: string;
  loading: boolean;
  reload: () => void;
};

const UNSUPPORTED_REASON = "desktop-only";

export function useProviders(projectRoot: string, enabled: boolean): ProviderState {
  const [inventory, setInventory] = useState<ProviderInventory | null>(null);
  const [loading, setLoading] = useState(false);
  const [reason, setReason] = useState<string>();
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !projectRoot) return;
    if (!isDesktopRuntime()) {
      setReason(UNSUPPORTED_REASON);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setReason(undefined);
    void invoke<ProviderInventory>("agent_providers", { projectPath: projectRoot })
      .then((result) => {
        if (cancelled) return;
        setInventory(result);
        setReason(result.reason);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Provider inventory unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, nonce, projectRoot]);

  return { providers: inventory?.providers ?? [], roles: inventory?.roles, reason, loading, reload };
}

export type SessionState = {
  sessions: readonly Session[];
  reason?: string;
  loading: boolean;
};

/** Reads the Agent's projection of the runtime's chat sessions. */
export function useSessions(projectRoot: string, enabled: boolean): SessionState {
  const [inventory, setInventory] = useState<SessionInventory | null>(null);
  const [loading, setLoading] = useState(false);
  const [reason, setReason] = useState<string>();

  useEffect(() => {
    if (!enabled || !projectRoot) return;
    if (!isDesktopRuntime()) {
      setReason(UNSUPPORTED_REASON);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setReason(undefined);
    void invoke<SessionInventory>("agent_sessions", { projectPath: projectRoot })
      .then((result) => {
        if (cancelled) return;
        setInventory(result);
        setReason(result.reason);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Sessions unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot]);

  return { sessions: inventory?.sessions ?? [], reason, loading };
}

export { UNSUPPORTED_REASON };
