import React from "react";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/locales/en";
import {
  type AccountUsage,
  type UsageWindow,
  describeAge,
  describeReset,
  useAccountUsage
} from "../accountUsage";
import { SOURCES } from "../sources";

/**
 * How much of each subscription account has been used.
 *
 * Every figure here was recorded by the CLI that owns the account, not fetched
 * from the vendor: Loopforge borrows a signed-in CLI and holds no credential of
 * its own, so there is nothing to authenticate a usage request with. That is
 * why each reading is dated and why an account with no readable figure says so
 * rather than being drawn at zero -- an empty bar and an unknown one look
 * identical, and only one of them is safe to act on.
 */

/**
 * Window labels, spelled out.
 *
 * A literal map rather than a cast: the same shortcut left three of five model
 * roles rendering as blank rows, and the vendor is free to introduce a window
 * this does not know, which falls back to the raw label instead of nothing.
 */
const WINDOW_LABEL: Record<string, MessageKey> = {
  "5h": "usage.window5h",
  "7d": "usage.window7d"
};

/**
 * What to call an account. Names are proper nouns and are not translated.
 *
 * The preset list covers the accounts reached through a borrowed CLI; anything
 * signed in directly carries its own name, because there is no preset to look
 * it up in and a bare `kimi` is not what the user chose.
 */
function accountName(account: AccountUsage): string {
  const preset = SOURCES.find((source) => source.providerId === account.provider_id);
  return preset?.name ?? account.display_name ?? account.provider_id;
}

function UsageBar({ window }: { window: UsageWindow }): React.JSX.Element {
  const { t, locale } = useI18n();
  const now = Date.now();
  // Clamped for drawing only -- the number beside it stays as reported, so a
  // vendor returning 105% is visible rather than quietly trimmed.
  const width = Math.max(0, Math.min(100, window.used_percent));
  const reset = describeReset(window.resets_at, now, locale);
  const label = WINDOW_LABEL[window.label];

  return (
    <div className="usage-window">
      <div className="usage-window-head">
        <span className="row-label">{label ? t(label) : window.label}</span>
        <span className="mono dim">
          {t("usage.used", { percent: window.used_percent })}
          {reset ? ` · ${t("usage.resets", { when: reset })}` : ""}
        </span>
      </div>
      <div
        className="usage-track"
        role="meter"
        aria-valuenow={window.used_percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ? t(label) : window.label}
      >
        <span
          className={`usage-fill${width >= 90 ? " bad" : ""}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function AccountCard({ account }: { account: AccountUsage }): React.JSX.Element {
  const { t, locale } = useI18n();
  const age = account.observed_at ? describeAge(account.observed_at, Date.now(), locale) : "";

  return (
    <div className="settings-card usage-card">
      <div className="usage-head">
        <span className="provider-name">{accountName(account)}</span>
        {account.plan && <span className="tag">{account.plan}</span>}
        {age && <span className="mono faint">{t("usage.recorded", { age })}</span>}
      </div>

      {account.available ? (
        <>
          {account.windows.map((window) => (
            <UsageBar key={window.window_minutes} window={window} />
          ))}
          {(account.credits_unlimited || account.credit_balance) && (
            <div className="settings-row">
              <div className="row-label">
                <span>{t("usage.credits")}</span>
              </div>
              <span className="mono dim">
                {account.credits_unlimited ? t("usage.unlimited") : account.credit_balance}
              </span>
            </div>
          )}
          {account.limit_id && (
            <div className="settings-row">
              <div className="row-label">
                <span>{t("usage.limit")}</span>
              </div>
              <span className="mono faint">{account.limit_id}</span>
            </div>
          )}
        </>
      ) : (
        <div className="usage-absent">
          <span className="mono faint">{t("usage.unavailable")}</span>
          {/* The reason comes from the reader and names the actual obstacle,
              which is what tells a user whether they can do anything about it. */}
          <p className="settings-note">{account.reason}</p>
        </div>
      )}
    </div>
  );
}

export function UsagePanel({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { accounts, reason, loading, reload } = useAccountUsage(projectRoot, true);

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("settings.group.usage")}</span>
        <button type="button" className="primary-button small" onClick={reload}>
          {t("usage.refresh")}
        </button>
      </div>

      <p className="settings-note">{t("usage.intro")}</p>

      {reason && <p className="settings-note">{reason}</p>}

      {!projectRoot ? (
        // The figures are read through the Agent, which runs per project, so
        // with none open there is nothing to ask -- which is not the same as
        // an answer of "no accounts".
        <p className="settings-note">{t("empty.noProjectTitle")}</p>
      ) : accounts.length === 0 ? (
        <p className="settings-note">{loading ? t("usage.loading") : t("usage.none")}</p>
      ) : (
        accounts.map((account) => <AccountCard key={account.provider_id} account={account} />)
      )}
    </>
  );
}
