import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Mirrors `loopforge-oauth-v1`.
 *
 * A subscription account is signed into here rather than borrowed from a CLI,
 * so Loopforge holds the grant and can ask the vendor things a borrowed
 * session could not -- how much of the plan is left, most usefully.
 *
 * Two sign-in shapes, because the vendors differ: one sends the user to a URL
 * and waits for a redirect, the other shows a short code to type on the
 * vendor's own page. Both end in the same place.
 */
export type AccountFlow = "callback" | "device_code";

export type Account = {
  id: string;
  name: string;
  flow: AccountFlow;
  signed_in: boolean;
  /**
   * Whether this account can be signed into here at all.
   *
   * A few need their client credentials supplied through the environment,
   * because they belong to the vendor rather than to Loopforge and this
   * repository is public. Offering a sign-in that cannot start is worse than
   * saying it is unavailable.
   */
  configured?: boolean;
  /**
   * Where this account's requests go, and in what shape.
   *
   * Taken from the account, not from the preset it was chosen under: a
   * vendor's API-key endpoint and its subscription endpoint differ, and two of
   * them speak a wire that is not OpenAI-compatible. Empty where no dispatch
   * endpoint is established -- the account can still be signed in and read for
   * usage, but is not somewhere a request is routed at a guess.
   */
  api_base_url?: string;
  protocol?: string;
  default_model?: string;
  account_label: string;
  plan: string;
  expires_at: string;
  /**
   * When the whole grant dies regardless of refreshes, for vendors that cap
   * it. Empty where there is no such cap.
   */
  grant_deadline: string;
};

type AccountList = { schema_version: string; accounts: readonly Account[] };

export type PendingSignIn = {
  provider_id: string;
  flow: AccountFlow;
  /** The page to open, or for a device flow the page to type the code on. */
  url: string;
  /** Empty for a redirect flow. */
  user_code: string;
};

const UNSUPPORTED_REASON = "Accounts are only available in the desktop app.";

export function useAccounts(projectRoot: string, enabled: boolean) {
  const [accounts, setAccounts] = useState<readonly Account[]>([]);
  const [reason, setReason] = useState<string>();
  const [loading, setLoading] = useState(false);
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
    void invoke<AccountList>("agent_oauth_accounts", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setAccounts(result?.accounts ?? []);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Accounts unavailable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, nonce, projectRoot]);

  return { accounts, reason, loading, reload, setAccounts };
}

export function beginSignIn(
  projectRoot: string,
  providerId: string
): Promise<PendingSignIn> {
  return invoke<PendingSignIn>("agent_oauth_begin", {
    projectPath: projectRoot,
    providerId
  });
}

/**
 * Waits for the user to finish at the vendor.
 *
 * Deliberately long-running: the promise is the wait. Nothing here polls, and
 * nothing here should be raced against a shorter timeout -- abandoning it
 * leaves the Agent holding a listener for a sign-in no one is watching.
 */
export function completeSignIn(
  projectRoot: string,
  providerId: string
): Promise<AccountList> {
  return invoke<AccountList>("agent_oauth_complete", {
    projectPath: projectRoot,
    providerId
  });
}

/**
 * Opens a URL in the user's own browser.
 *
 * Through the shell rather than `window.open`: a webview may open it in a
 * frame the vendor's sign-in refuses to run in, and the whole point is that
 * the user sees the page in the browser they already trust.
 */
export function openExternal(url: string): Promise<void> {
  return invoke<void>("open_external", { url });
}

export function signOut(projectRoot: string, providerId: string): Promise<AccountList> {
  return invoke<AccountList>("agent_oauth_sign_out", {
    projectPath: projectRoot,
    providerId
  });
}

/**
 * How long until a grant has to be re-established interactively.
 *
 * Returned in days because that is the unit the warning is useful in: these
 * caps are measured in weeks, and "expires in 3 days" is something a user can
 * act on before it strands them mid-session.
 *
 * Rounded up, so the figure is the number of days the user still has. Rounding
 * down reports a deadline three days out as two -- a warning that is wrong in
 * the direction of panic, and off by one from the date the vendor will act on.
 */
export function daysUntil(deadline: string, now: number): number | null {
  const at = Date.parse(deadline);
  if (Number.isNaN(at)) return null;
  return Math.ceil((at - now) / 86_400_000);
}
