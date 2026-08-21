import React, { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { Icon } from "../icons";
import { useKey } from "./primitives";
import {
  ACCOUNT_DETAILS,
  PAIR_CODE,
  PROTOCOLS,
  PROVIDER_SOURCES,
  type ProviderSource,
  modelsForSource
} from "../fixtures.providers";

type AccountStage = "idle" | "waiting" | "done";

function sourceMark(label: string): string {
  const stripped = label.replace(/[^A-Za-z一-龥]/g, "");
  return stripped.slice(0, 2).toUpperCase();
}

/**
 * Three-step Add Provider wizard from the Workbench design.
 *
 * Preview only: the Workbench does not store credentials — the Loopforge Agent
 * owns provider configuration — so nothing entered here is persisted, and the
 * footer says so on every step.
 */
export function AddProvider({ onClose }: { onClose: () => void }): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();
  const [step, setStep] = useState(1);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<ProviderSource>(PROVIDER_SOURCES[0]);
  const [protocol, setProtocol] = useState(1);
  const [stage, setStage] = useState<AccountStage>("idle");
  const [fetched, setFetched] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [excluded, setExcluded] = useState<Readonly<Record<number, boolean>>>({});
  const [roles, setRoles] = useState<Readonly<Record<number, string>>>({});

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return PROVIDER_SOURCES;
    return PROVIDER_SOURCES.filter(
      (candidate) =>
        candidate.label.toLowerCase().includes(needle) ||
        candidate.note.toLowerCase().includes(needle)
    );
  }, [query]);

  const isAccount = source.kind === "account";
  const isCustom = source.kind === "custom";
  const isLocal = source.kind === "local";
  const models = fetched ? modelsForSource(source.label) : [];
  const chosen = models.filter((_model, index) => !excluded[index]).length;
  const account = ACCOUNT_DETAILS[source.label] ?? ACCOUNT_DETAILS["Claude Code subscription"];

  const next = (): void => {
    if (step === 2 && isAccount && stage !== "done") {
      setStage("waiting");
      return;
    }
    if (step < 3) {
      setStep(step + 1);
      if (isAccount) setFetched(true);
      return;
    }
    onClose();
  };

  const nextLabel =
    step === 2 && isAccount && stage !== "done"
      ? t("wizard.signIn")
      : step < 3
        ? t("wizard.next")
        : t("wizard.addModels", { count: chosen });

  const fetchLabel = fetched
    ? t("wizard.fetched", { count: models.length })
    : isAccount
      ? t("wizard.fetchAccount")
      : isLocal
        ? t("wizard.fetchLocal")
        : t("wizard.fetch");

  const fetchHint = fetched
    ? t("wizard.fetchHintDone")
    : isCustom
      ? t("wizard.fetchHintManual")
      : isLocal
        ? t("wizard.fetchHintLocal")
        : t("wizard.fetchHint");

  const connectionHint = isAccount
    ? t("wizard.hint.account")
    : isLocal
      ? t("wizard.hint.local")
      : isCustom
        ? t("wizard.hint.custom")
        : t("wizard.hint.cloud");

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal wizard"
        role="dialog"
        aria-modal="true"
        aria-label={t("wizard.title")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("wizard.title")}</strong>
          <ol className="wizard-steps">
            {(["source", "connection", "models"] as const).map((name, index) => {
              const n = index + 1;
              return (
                <li
                  key={name}
                  className={step === n ? "active" : step > n ? "done" : ""}
                >
                  <span className="step-n">{n}</span>
                  {t(`wizard.step.${name}` as never)}
                </li>
              );
            })}
          </ol>
        </header>

        <div className="modal-body">
          {step === 1 && (
            <>
              <div className="wizard-search">
                <span className="search-icon" aria-hidden="true">
                  <Icon name="search" size={13} />
                </span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t("wizard.search")}
                  aria-label={t("wizard.search")}
                />
                <span className="mono faint">
                  {query
                    ? t("wizard.matchCount", {
                        matched: matches.length,
                        total: PROVIDER_SOURCES.length
                      })
                    : t("wizard.sourceCount", { count: PROVIDER_SOURCES.length })}
                </span>
              </div>
              <div className="source-list">
                {matches.map((candidate) => (
                  <button
                    key={candidate.label}
                    type="button"
                    className={
                      candidate.label === source.label ? "source-row selected" : "source-row"
                    }
                    onClick={() => {
                      setSource(candidate);
                      setStep(2);
                      setFetched(false);
                      setExcluded({});
                      setExpanded(null);
                      setStage("idle");
                    }}
                  >
                    <span className={`source-mark kind-${candidate.kind}`}>
                      {sourceMark(candidate.label)}
                    </span>
                    <span className="source-identity">
                      <span className="source-name">{candidate.label}</span>
                      <span className="mono faint truncate">{candidate.note}</span>
                    </span>
                    <span className="tag">{key("provider.kind", candidate.kind)}</span>
                  </button>
                ))}
                {matches.length === 0 && <p className="wizard-empty">{t("wizard.noMatch")}</p>}
              </div>
            </>
          )}

          {step === 2 && (
            <>
              {isAccount ? (
                <div className="account-card">
                  <div className="account-head">
                    <span className="source-mark kind-account">{account.mark}</span>
                    <span className="source-identity">
                      <span className="source-name">{account.title}</span>
                      <span className="faint">{t("wizard.hint.account")}</span>
                    </span>
                    <span className={`badge ${stage === "done" ? "ok" : stage === "waiting" ? "accent" : ""}`}>
                      {t(`wizard.badge.${stage}` as never)}
                    </span>
                  </div>

                  {stage === "idle" && (
                    <button type="button" className="primary-button wide" onClick={() => setStage("waiting")}>
                      {t("wizard.signIn")}
                    </button>
                  )}

                  {stage === "waiting" && (
                    <div className="account-waiting">
                      <p className="waiting-banner">
                        <span className="spinner" aria-hidden="true" />
                        {t("wizard.waiting")}
                      </p>
                      <div className="pair-row">
                        <span className="faint">{t("wizard.pairCode")}</span>
                        <strong className="pair-code mono">{PAIR_CODE}</strong>
                        <button
                          type="button"
                          className="secondary-button small"
                          onClick={() => setStage("done")}
                        >
                          {t("wizard.confirmed")}
                        </button>
                      </div>
                    </div>
                  )}

                  {stage === "done" && (
                    <div className="account-done">
                      <div className="detail-row">
                        <span className="faint">{t("wizard.acctModels")}</span>
                        <span className="mono dim">{account.models}</span>
                      </div>
                      <div className="detail-row">
                        <span className="faint">{t("wizard.acctToken")}</span>
                        <span className="mono dim">{t("wizard.acctTokenValue")}</span>
                      </div>
                      <button type="button" className="text-danger" onClick={() => setStage("idle")}>
                        {t("wizard.signOut")}
                      </button>
                    </div>
                  )}

                  <p className="wizard-note">{t("wizard.acctNote")}</p>
                </div>
              ) : (
                <>
                  {isCustom && (
                    <div className="field-block">
                      <span className="field-label">{t("wizard.protocol")}</span>
                      <div className="protocol-list" role="radiogroup" aria-label={t("wizard.protocol")}>
                        {PROTOCOLS.map((candidate, index) => (
                          <button
                            key={candidate.label}
                            type="button"
                            role="radio"
                            aria-checked={protocol === index}
                            className={protocol === index ? "protocol-row selected" : "protocol-row"}
                            onClick={() => setProtocol(index)}
                          >
                            <span className="radio-dot" aria-hidden="true" />
                            <span className="source-identity">
                              <span className="source-name">{candidate.label}</span>
                              <span className="mono faint">{candidate.path}</span>
                            </span>
                            <span className="faint truncate">{key("protocol", candidate.note)}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="field-block">
                    <span className="field-label">{t("wizard.displayName")}</span>
                    <div className="field-value mono">{source.label}</div>
                  </div>
                  {(isLocal || isCustom) && (
                    <div className="field-block">
                      <span className="field-label">{t("provider.field.baseUrl")}</span>
                      <div className="field-value mono faint">
                        {isCustom ? "https://…/v1" : `http://${source.note.split(" ")[0]}/v1`}
                      </div>
                    </div>
                  )}
                  {!isLocal && (
                    <div className="field-block">
                      <span className="field-label">{t("provider.field.apiKey")}</span>
                      <div className="field-value mono faint">sk-…</div>
                    </div>
                  )}
                </>
              )}
              {!isAccount && <p className="wizard-note">{connectionHint}</p>}
            </>
          )}

          {step === 3 && (
            <>
              <div className="wizard-search plain">
                <span className="faint">{fetchHint}</span>
                <button
                  type="button"
                  className="secondary-button small"
                  onClick={() => setFetched(true)}
                >
                  {fetchLabel}
                </button>
                <button
                  type="button"
                  className="secondary-button small"
                  onClick={() => {
                    setFetched(true);
                    setExpanded(0);
                  }}
                >
                  {t("wizard.addManual")}
                </button>
              </div>
              <div className="source-list">
                {models.map((model, index) => {
                  const on = !excluded[index];
                  const open = expanded === index;
                  const role = roles[index] ?? model.role;
                  return (
                    <div key={model.name} className="model-choice">
                      <div className="model-choice-head">
                        <button
                          type="button"
                          role="checkbox"
                          aria-checked={on}
                          aria-label={model.name}
                          className={on ? "checkbox on" : "checkbox"}
                          onClick={() =>
                            setExcluded((current) => ({ ...current, [index]: on }))
                          }
                        >
                          {on && <Icon name="check" size={10} />}
                        </button>
                        <button
                          type="button"
                          className="model-choice-name"
                          onClick={() => setExpanded(open ? null : index)}
                          aria-expanded={open}
                        >
                          <span className={on ? "mono" : "mono faint"}>{model.name}</span>
                          <span className="mono faint">{model.caps.join(" · ")}</span>
                        </button>
                        <span className={open ? "chevron open" : "chevron"} aria-hidden="true">
                          <Icon name="chevron" size={12} />
                        </span>
                      </div>
                      {open && (
                        <div className="model-choice-body">
                          <div className="detail-row">
                            <span className="faint">{t("provider.contextWindow")}</span>
                            <span className="mono dim">{model.ctx}</span>
                          </div>
                          <div className="detail-row">
                            <span className="faint">{t("provider.maxOutput")}</span>
                            <span className="mono dim">{model.maxOut}</span>
                          </div>
                          <div className="detail-row">
                            <span className="faint">{t("wizard.alias")}</span>
                            <span className="mono dim">{model.alias}</span>
                          </div>
                          <div className="detail-row">
                            <span className="faint">{t("wizard.roleRouting")}</span>
                            <span className="role-chips">
                              {(["primary", "fast", "vision", "none"] as const).map((candidate) => (
                                <button
                                  key={candidate}
                                  type="button"
                                  className={role === candidate ? "role-chip active" : "role-chip"}
                                  onClick={() =>
                                    setRoles((current) => ({ ...current, [index]: candidate }))
                                  }
                                >
                                  {key("role", candidate)}
                                </button>
                              ))}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">
            {step === 1
              ? t("wizard.footer.source")
              : step === 2
                ? connectionHint
                : t("wizard.footer.models")}
          </span>
          <div className="card-actions">
            {step > 1 && (
              <button type="button" className="secondary-button" onClick={() => setStep(step - 1)}>
                {t("wizard.back")}
              </button>
            )}
            <button type="button" className="secondary-button" onClick={onClose}>
              {t("action.cancel")}
            </button>
            <button type="button" className="primary-button" onClick={next}>
              {nextLabel}
            </button>
          </div>
        </footer>
        <p className="modal-disclaimer">{t("wizard.notPersisted")}</p>
      </div>
    </div>
  );
}
