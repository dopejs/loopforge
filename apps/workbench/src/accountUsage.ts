import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-account-usage-v1`.
 *
 * A subscription account is reached by borrowing a CLI the user has already
 * signed into, so Loopforge holds no credential for it and cannot ask the
 * vendor how much is left. Everything here is what that CLI wrote to disk,
 * which is why `observed_at` is part of the record rather than an extra: the
 * figure can be hours old and must never be drawn as though it were current.
 *
 * An account with nothing readable still arrives, carrying `reason`. Filtering
 * those out would read as "no such account" instead of "no figure".
 */
export type UsageWindow = {
  /** `5h`, `7d`, or the raw duration when the vendor reports a new one. */
  label: string;
  window_minutes: number;
  used_percent: number;
  /** Empty when the vendor did not say when the window rolls over. */
  resets_at: string;
};

export type AccountUsage = {
  provider_id: string;
  available: boolean;
  reason: string;
  observed_at: string;
  plan: string;
  limit_id: string;
  windows: readonly UsageWindow[];
  credit_balance: string;
  credits_unlimited: boolean;
  /** `vendor` when the account answered, `local` when read from a CLI's records. */
  source?: string;
  /** The vendor's own name, for accounts no endpoint preset covers. */
  display_name?: string;
};

type UsageReport = {
  schema_version: string;
  accounts: readonly AccountUsage[];
};

const UNSUPPORTED_REASON = "Account usage is only available in the desktop app.";

export type AccountUsageState = {
  accounts: readonly AccountUsage[];
  reason?: string;
  loading: boolean;
  reload: () => void;
};

export function useAccountUsage(projectRoot: string, enabled: boolean): AccountUsageState {
  const [accounts, setAccounts] = useState<readonly AccountUsage[]>([]);
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
    void invoke<UsageReport>("agent_account_usage", { projectPath: projectRoot })
      .then((result) => {
        if (cancelled) return;
        setAccounts(result?.accounts ?? []);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Account usage unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, nonce, projectRoot]);

  return { accounts, reason, loading, reload };
}

/**
 * How long ago a figure was recorded.
 *
 * `Intl.RelativeTimeFormat` rather than eight hand-written catalogues of
 * "2h ago": the runtime already knows how every supported locale phrases
 * this, and a translated string per unit is a set of keys that would drift.
 *
 * Rounded towards zero deliberately: a reading is at least this old, never
 * less, and rounding up would make a fresh figure look stale.
 */
export function describeAge(observedAt: string, now: number, locale: string): string {
  const recorded = Date.parse(observedAt);
  if (Number.isNaN(recorded)) return "";
  return relative(recorded - now, locale);
}

/**
 * When a window rolls over, or empty when the vendor did not say.
 *
 * A reset already in the past still reads as the past rather than as a
 * negative countdown: the window has rolled over, so the figure beside it
 * describes a period that has ended.
 */
export function describeReset(resetsAt: string, now: number, locale: string): string {
  const resets = Date.parse(resetsAt);
  if (Number.isNaN(resets)) return "";
  return relative(resets - now, locale);
}

/** A signed millisecond offset in the largest unit that keeps it above one. */
function relative(deltaMs: number, locale: string): string {
  const format = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const minutes = Math.trunc(deltaMs / 60_000);
  if (Math.abs(minutes) < 60) return format.format(minutes, "minute");
  const hours = Math.trunc(minutes / 60);
  if (Math.abs(hours) < 24) return format.format(hours, "hour");
  return format.format(Math.trunc(hours / 24), "day");
}
