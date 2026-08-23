import React, { useState } from "react";
import { useI18n } from "../i18n";
import {
  type Account,
  type PendingSignIn,
  beginSignIn,
  completeSignIn,
  daysUntil,
  openExternal,
  signOut,
  useAccounts
} from "../accounts";
import { errorMessage } from "../daemon";

/**
 * Signing subscription accounts in.
 *
 * Loopforge signs in as the vendor's own client and holds the grant, which is
 * what lets a subscription be used without that vendor's CLI installed and
 * what makes its remaining allowance readable. The two flows differ in what
 * the user has to do -- follow a redirect, or type a short code -- and the
 * panel shows only the one that applies rather than explaining both.
 *
 * Signing out is described as local, because it is: the grant here is
 * forgotten and nothing is revoked at the vendor.
 */

/** Warn this far ahead of a grant's absolute expiry. */
const DEADLINE_WARNING_DAYS = 7;

function Deadline({ account }: { account: Account }): React.JSX.Element | null {
  const { t } = useI18n();
  if (!account.signed_in || !account.grant_deadline) return null;
  const days = daysUntil(account.grant_deadline, Date.now());
  if (days === null || days > DEADLINE_WARNING_DAYS) return null;
  // Some vendors end the whole grant a fixed time after the interactive login
  // however healthily it has refreshed since, so this is the one expiry a
  // user has to act on rather than one that renews itself.
  return (
    <span className="mono faint">
      {days <= 0 ? t("account.expiresSoon") : t("account.expiresIn", { days })}
    </span>
  );
}

function AccountRow({
  account,
  projectRoot,
  onChanged
}: {
  account: Account;
  projectRoot: string;
  onChanged: (accounts: readonly Account[]) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [pending, setPending] = useState<PendingSignIn | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  async function start(): Promise<void> {
    setFailure("");
    setBusy(true);
    try {
      const started = await beginSignIn(projectRoot, account.id);
      setPending(started);
      // Opened after the listener exists, never before: the Agent binds the
      // redirect port first, so a browser sent early would find nothing there.
      void openExternal(started.url).catch(() => {
        // The URL is on screen either way; a shell that cannot open a browser
        // is not a reason to fail the sign-in.
      });
      const result = await completeSignIn(projectRoot, account.id);
      onChanged(result.accounts ?? []);
      setPending(null);
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("account.failed")));
      setPending(null);
    } finally {
      setBusy(false);
    }
  }

  async function leave(): Promise<void> {
    setBusy(true);
    try {
      const result = await signOut(projectRoot, account.id);
      onChanged(result.accounts ?? []);
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("account.failed")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-row account-row">
      <div className="row-label">
        <span>{account.name}</span>
        <small>
          {account.signed_in
            ? account.account_label || t("account.signedIn")
            : account.flow === "device_code"
              ? "device code"
              : ""}
        </small>
      </div>

      <div className="account-state">
        {account.plan && <span className="tag">{account.plan}</span>}
        <Deadline account={account} />
        {account.signed_in ? (
          <button type="button" className="ghost-button small" disabled={busy} onClick={leave}>
            {t("account.signOut")}
          </button>
        ) : (
          <button
            type="button"
            className="primary-button small"
            disabled={busy || account.configured === false}
            onClick={start}
          >
            {t("account.signIn")}
          </button>
        )}
      </div>

      {pending && (
        <div className="account-pending">
          {/* A device flow's code is the whole instruction, so it is shown
              rather than described. */}
          {pending.user_code ? (
            <>
              <span>{t("account.enterCode")}</span>
              <code className="device-code">{pending.user_code}</code>
            </>
          ) : (
            <span>{t("account.waiting")}</span>
          )}
          <a href={pending.url} target="_blank" rel="noreferrer" className="mono">
            {t("account.openPage")}
          </a>
        </div>
      )}

      {failure && <p className="settings-note issue-line">{failure}</p>}
    </div>
  );
}

export function AccountsPanel({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { accounts, reason, loading, setAccounts } = useAccounts(projectRoot, true);

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("account.section")}</span>
      </div>
      <p className="settings-note">{t("account.intro")}</p>

      {reason && <p className="settings-note issue-line">{reason}</p>}

      {accounts.length === 0 ? (
        <p className="settings-note">{loading ? t("usage.loading") : t("usage.none")}</p>
      ) : (
        <>
          <div className="settings-card">
            {accounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                projectRoot={projectRoot}
                onChanged={setAccounts}
              />
            ))}
          </div>
          <p className="settings-note faint">{t("account.localOnly")}</p>
        </>
      )}
    </>
  );
}
