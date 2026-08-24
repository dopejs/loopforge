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

/**
 * Mirrors `loopforge-settings-v1`.
 *
 * The credential is never carried: `has_api_key` says whether one is stored,
 * which is all a surface needs. Reading it back would put it in a response, a
 * log and a renderer for no purpose the user has.
 */
export type ProviderSettings = {
  schema_version: "loopforge-settings-v1";
  provider_id: string;
  base_url?: string;
  model?: string;
  display_name?: string;
  protocol?: string;
  has_api_key?: boolean;
  configured?: boolean;
  updated_at?: string;
  /** Kura reads provider configuration at boot, so a save is not yet live. */
  restart_required?: boolean;
  reason?: string;
};

export function useProviderSettings(projectRoot: string, enabled: boolean) {
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [reason, setReason] = useState<string>();
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !projectRoot || !isDesktopRuntime()) return;
    let cancelled = false;
    void invoke<ProviderSettings>("agent_provider_settings", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setSettings(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Provider settings unavailable"));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { settings, reason, reload };
}

/** Saves the endpoint. An empty key keeps the stored one. */
export function saveProviderSettings(
  projectRoot: string,
  input: {
    base_url: string;
    api_key: string;
    model: string;
    display_name?: string;
    protocol?: string;
    /**
     * A signed-in account to draw the credential from, instead of a typed key.
     *
     * When set, the stored key becomes a cache of the last access token: it is
     * refreshed before each dispatch rather than asked for again, because an
     * OAuth token expires in about an hour.
     */
    oauth_provider_id?: string;
    /**
     * The id this provider is stored and dispatched under.
     *
     * Taken from the source the user chose, so adding a second provider adds
     * one rather than overwriting the first. Everything used to land in a
     * single slot named `openai_compatible`, which is what an endpoint came
     * back called however it had been named.
     */
    provider_id?: string;
  }
): Promise<ProviderSettings> {
  return invoke<ProviderSettings>("agent_save_provider_settings", {
    projectPath: projectRoot,
    baseUrl: input.base_url,
    apiKey: input.api_key,
    model: input.model,
    displayName: input.display_name ?? "",
    protocol: input.protocol ?? "",
    oauthProviderId: input.oauth_provider_id ?? "",
    providerId: input.provider_id ?? ""
  });
}

/**
 * Points one modality at a provider.
 *
 * Routing is a Kura capability; this forwards through the Agent so the
 * Workbench never reaches the runtime itself.
 */
export function routeModelRole(
  projectRoot: string,
  role: string,
  providerId: string,
  model = ""
): Promise<ProviderInventory> {
  return invoke<ProviderInventory>("agent_route_role", {
    projectPath: projectRoot,
    role,
    providerId,
    model
  });
}

export function clearModelRole(
  projectRoot: string,
  role: string
): Promise<ProviderInventory> {
  return invoke<ProviderInventory>("agent_clear_role", { projectPath: projectRoot, role });
}

/** Removes one provider by id, on disk and in the running runtime. */
export function forgetProviderSettings(
  projectRoot: string,
  providerId: string
): Promise<ProviderSettings> {
  return invoke<ProviderSettings>("agent_forget_provider_settings", {
    projectPath: projectRoot,
    providerId
  });
}

/**
 * Mirrors `loopforge-provider-auth-v1`.
 *
 * `checked` is false when nothing has looked at this provider yet -- the
 * runtime keeps auth state only once something has. That is a state to render,
 * not an error, and it is why the first thing the surface offers is a check.
 */

/**
 * Asks an endpoint what models it serves, before anything is stored.
 *
 * Goes straight out rather than through Kura, which reads its provider
 * configuration at startup and so cannot answer for an endpoint still being
 * typed. It doubles as the connection check: a wrong key answers 401 here
 * instead of failing a conversation after a restart.
 */
/** What an endpoint answered when asked for its model list. */
export type ProviderProbe = {
  schema_version: string;
  reachable: boolean;
  /** The status it answered with, where it answered at all. */
  status?: number;
  models: readonly string[];
  error?: string;
};

export function probeProvider(
  projectRoot: string,
  baseUrl: string,
  apiKey: string,
  protocol = "openai_compatible",
  /** A signed-in account to draw the credential from, instead of a key. */
  oauthProviderId = ""
): Promise<ProviderProbe> {
  return invoke<ProviderProbe>("agent_probe_provider", {
    projectPath: projectRoot,
    baseUrl,
    apiKey,
    protocol,
    oauthProviderId
  });
}
