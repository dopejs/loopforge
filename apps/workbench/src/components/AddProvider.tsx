import React, { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  type Provider,
  forgetProviderSettings,
  saveProviderSettings,
  useProviderSettings
} from "../providers";
import { useKey } from "./primitives";

/**
 * Configuring the model endpoint.
 *
 * This was previously read-only: it listed the providers Kura exposes and
 * explained what each one needed, on the reasoning that credentials belong to
 * the Agent's configuration rather than the Workbench. That reasoning was
 * right and the result was a dead end -- there was no way to reach that
 * configuration, so a user holding a base URL and a key had nowhere to put
 * them.
 *
 * The Workbench still does not keep the credential. It is passed to the Agent,
 * which stores it once per machine under `~/.loopforge` rather than once per
 * project, and hands it to Kura at startup. It is never read back: the form
 * shows whether a key is set, not what it is.
 */
export function AddProvider({
  providers,
  projectRoot,
  onClose,
  onSaved
}: {
  providers: readonly Provider[];
  projectRoot: string;
  onClose: () => void;
  onSaved?: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();
  const { settings, reload } = useProviderSettings(projectRoot, true);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<string>();

  // Seeded from what is stored, except the key, which is never sent back.
  useEffect(() => {
    if (!settings) return;
    setBaseUrl(settings.base_url ?? "");
    setModel(settings.model ?? "");
  }, [settings]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const run = async (action: () => Promise<unknown>): Promise<void> => {
    if (busy || !isDesktopRuntime()) return;
    setBusy(true);
    setFailure(undefined);
    try {
      await action();
      setApiKey("");
      setSaved(true);
      reload();
      onSaved?.();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("settings.provider.saveFailed")));
    } finally {
      setBusy(false);
    }
  };

  const hasKey = settings?.has_api_key === true;

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("wizard.title")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("wizard.title")}</strong>
          <p className="wizard-note">{t("wizard.intro")}</p>
        </header>

        <div className="modal-body">
          <label className="hypothesis-field">
            <span className="hypothesis-field-head">
              <span>{t("settings.provider.baseUrl")}</span>
            </span>
            <input
              className="hypothesis-brief"
              value={baseUrl}
              placeholder="https://api.example.com/v1"
              onChange={(event) => {
                setBaseUrl(event.target.value);
                setSaved(false);
              }}
            />
          </label>

          <label className="hypothesis-field">
            <span className="hypothesis-field-head">
              <span>{t("settings.provider.model")}</span>
            </span>
            <input
              className="hypothesis-brief"
              value={model}
              placeholder="gpt-4o-mini"
              onChange={(event) => {
                setModel(event.target.value);
                setSaved(false);
              }}
            />
          </label>

          <label className="hypothesis-field">
            <span className="hypothesis-field-head">
              <span>{t("settings.provider.apiKey")}</span>
              {hasKey && <span className="badge ok">{t("settings.provider.keySet")}</span>}
            </span>
            <input
              className="hypothesis-brief"
              type="password"
              value={apiKey}
              placeholder={hasKey ? t("settings.provider.keyKept") : t("settings.provider.keyNew")}
              onChange={(event) => {
                setApiKey(event.target.value);
                setSaved(false);
              }}
            />
          </label>
          {/*
            Said plainly rather than left to be discovered: the key is on this
            machine in a file, not in a keychain, and it is not encrypted.
          */}
          <p className="settings-note">{t("settings.provider.storageNote")}</p>

          {saved && <p className="settings-note">{t("settings.provider.restart")}</p>}
          {failure && <p className="settings-note tone-bad">{failure}</p>}

          {providers.length > 0 && (
            <>
              <div className="settings-section">
                <span className="section-title">{t("settings.provider.runtime")}</span>
              </div>
              <div className="source-list">
                {providers.map((provider) => (
                  <div key={provider.id} className="model-choice">
                    <div className="model-choice-head">
                      <span
                        className={`state-dot ${provider.health === "ready" ? "ok" : provider.health === "error" ? "bad" : "off"}`}
                        aria-hidden="true"
                      />
                      <span className="source-identity">
                        <span className="source-name">{provider.title}</span>
                        <span className="mono faint truncate">
                          {provider.base_url || provider.family}
                        </span>
                      </span>
                      <span className={`badge ${provider.ready ? "ok" : ""}`}>
                        {key("provider.status", provider.health)}
                      </span>
                    </div>
                    {/* The runtime's own issues, verbatim: they name exactly
                        what is missing. */}
                    {provider.issues && provider.issues.length > 0 && (
                      <div className="model-choice-body">
                        <ul className="issue-list">
                          {provider.issues.map((issue) => (
                            <li key={issue}>{issue}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">{t("wizard.credentialsNote")}</span>
          <div className="card-actions">
            {hasKey && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => void run(() => forgetProviderSettings(projectRoot))}
                disabled={busy}
              >
                {t("settings.provider.forget")}
              </button>
            )}
            <button type="button" className="secondary-button" onClick={onClose}>
              {t("action.close")}
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() =>
                void run(() =>
                  saveProviderSettings(projectRoot, {
                    base_url: baseUrl,
                    api_key: apiKey,
                    model
                  })
                )
              }
              disabled={busy || !isDesktopRuntime()}
            >
              {busy ? t("settings.provider.saving") : t("settings.provider.save")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
