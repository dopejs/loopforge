import React from "react";
import { useI18n } from "../i18n";
import { type Provider } from "../providers";
import { useKey } from "./primitives";

/**
 * How to make a provider usable.
 *
 * The design mocked a three-step wizard over thirty sources. Kura does not work
 * that way: it exposes a fixed set of providers, and the user configures one
 * rather than adding an arbitrary endpoint. Presenting a catalogue would offer
 * choices that cannot be made.
 *
 * Configuration itself is not performed here. Base URL, key and model reach the
 * daemon through its configuration, and the Workbench does not hold
 * credentials — so this explains precisely what each provider needs and what
 * is currently missing, using the runtime's own reported issues.
 */
export function AddProvider({
  providers,
  onClose
}: {
  providers: readonly Provider[];
  onClose: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

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
          {providers.length === 0 ? (
            <p className="wizard-empty">{t("provider.unavailable")}</p>
          ) : (
            <div className="source-list">
              {providers.map((provider) => (
                <div key={provider.id} className="model-choice">
                  <div className="model-choice-head">
                    <span className={`state-dot ${provider.health === "ready" ? "ok" : provider.health === "error" ? "bad" : "off"}`} aria-hidden="true" />
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
                  <div className="model-choice-body">
                    {/*
                      The runtime's own issues, verbatim: they name exactly what
                      is missing, which is more useful than a generic hint.
                    */}
                    {provider.issues && provider.issues.length > 0 ? (
                      <ul className="issue-list">
                        {provider.issues.map((issue) => (
                          <li key={issue}>{issue}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="faint">{t("wizard.providerReady")}</p>
                    )}
                    <p className="faint">
                      {key("wizard.howTo", provider.auth_mode || "unknown")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">{t("wizard.credentialsNote")}</span>
          <div className="card-actions">
            <button type="button" className="primary-button" onClick={onClose}>
              {t("action.close")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
