import React, { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  type Provider,
  clearModelRole,
  forgetProviderSettings,
  routeModelRole,
  saveProviderSettings,
  useProviderSettings,
  useProviders
} from "../providers";
import {
  type Source,
  matchSources,
  needsApiKey,
  sourceForBaseUrl,
  SOURCES
} from "../sources";
import type { MessageKey } from "../i18n/locales/en";

type Step = "source" | "connection" | "models";

const STEPS: readonly Step[] = ["source", "connection", "models"];

const STEP_LABEL: Record<Step, MessageKey> = {
  source: "wizard.step.source",
  connection: "wizard.step.connection",
  models: "wizard.step.models"
};

const KIND_HINT: Record<Source["kind"], MessageKey> = {
  cloud: "wizard.hint.cloud",
  local: "wizard.hint.local",
  custom: "wizard.hint.custom"
};

/**
 * Adding a model provider, in the three steps the design lays out: pick a
 * source, connect it, then decide what its models are used for.
 *
 * The sources are presets over one protocol rather than distinct providers.
 * Kura implements exactly one HTTP provider, so choosing "DeepSeek" fills in
 * an endpoint the user would otherwise have to look up and nothing more. That
 * is worth doing -- knowing a vendor's base URL by heart is not a reasonable
 * thing to require -- but it is not a catalogue of integrations, and the
 * wizard does not pretend otherwise.
 *
 * The Workbench never keeps the credential. It goes to the Agent, which stores
 * it once per machine and hands it to Kura at startup, and is never read back:
 * the form shows whether a key is set, not what it is.
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
  const { settings, reload } = useProviderSettings(projectRoot, true);

  const [step, setStep] = useState<Step>("source");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<Source | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<string>();

  // An endpoint already configured reopens on its own source, so revisiting
  // the wizard is editing rather than starting over.
  useEffect(() => {
    if (!settings?.base_url || source) return;
    const known = sourceForBaseUrl(settings.base_url) ?? SOURCES[SOURCES.length - 1];
    setSource(known);
    setBaseUrl(settings.base_url);
    setModel(settings.model ?? "");
    setDisplayName(settings.display_name || known.name);
    setStep("connection");
  }, [settings, source]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const matches = useMemo(() => matchSources(query), [query]);

  const choose = (picked: Source): void => {
    setSource(picked);
    setBaseUrl(picked.baseUrl);
    setDisplayName(picked.name);
    if (!model && picked.exampleModel) setModel(picked.exampleModel);
    setStep("connection");
    setFailure(undefined);
  };

  const save = async (): Promise<void> => {
    if (busy || !source || !isDesktopRuntime()) return;
    setBusy(true);
    setFailure(undefined);
    try {
      await saveProviderSettings(projectRoot, {
        base_url: baseUrl,
        api_key: apiKey,
        model,
        display_name: displayName,
        protocol: source.protocol
      });
      setApiKey("");
      setSaved(true);
      reload();
      onSaved?.();
      setStep("models");
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("settings.provider.saveFailed")));
    } finally {
      setBusy(false);
    }
  };

  const hasKey = settings?.has_api_key === true;
  const keyRequired = source ? needsApiKey(source) : true;
  const canSave = Boolean(baseUrl.trim() && model.trim() && (!keyRequired || apiKey || hasKey));

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
            {STEPS.map((name, index) => (
              <li
                key={name}
                className={
                  name === step
                    ? "wizard-step current"
                    : STEPS.indexOf(step) > index
                      ? "wizard-step done"
                      : "wizard-step"
                }
              >
                <span className="wizard-step-index">{index + 1}</span>
                {t(STEP_LABEL[name])}
              </li>
            ))}
          </ol>
        </header>

        <div className="modal-body">
          {step === "source" && (
            <SourceStep
              query={query}
              matches={matches}
              onQuery={setQuery}
              onChoose={choose}
            />
          )}

          {step === "connection" && source && (
            <ConnectionStep
              source={source}
              displayName={displayName}
              baseUrl={baseUrl}
              model={model}
              apiKey={apiKey}
              hasKey={hasKey}
              onDisplayName={setDisplayName}
              onBaseUrl={setBaseUrl}
              onModel={setModel}
              onApiKey={setApiKey}
            />
          )}

          {step === "models" && (
            <ModelsStep projectRoot={projectRoot} providers={providers} saved={saved} />
          )}

          {failure && <p className="wizard-note tone-bad">{failure}</p>}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">
            {step === "source"
              ? t("wizard.footer.source")
              : step === "models"
                ? t("wizard.footer.models")
                : t("settings.provider.storageNote")}
          </span>
          <div className="card-actions">
            {step !== "source" && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => setStep(step === "models" ? "connection" : "source")}
              >
                {t("wizard.back")}
              </button>
            )}
            {step === "connection" && hasKey && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  void forgetProviderSettings(projectRoot).then(() => {
                    reload();
                    setStep("source");
                    setSource(null);
                  });
                }}
                disabled={busy}
              >
                {t("settings.provider.forget")}
              </button>
            )}
            <button type="button" className="secondary-button" onClick={onClose}>
              {t("action.close")}
            </button>
            {step === "connection" && (
              <button
                type="button"
                className="primary-button"
                onClick={() => void save()}
                // Not disabled on validity alone: the Agent decides whether an
                // endpoint is acceptable, and its refusal names the reason.
                disabled={busy || !canSave}
              >
                {busy ? t("settings.provider.saving") : t("wizard.next")}
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

/** Step one: which source, out of the ones this protocol reaches. */
function SourceStep({
  query,
  matches,
  onQuery,
  onChoose
}: {
  query: string;
  matches: readonly Source[];
  onQuery: (value: string) => void;
  onChoose: (source: Source) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  return (
    <>
      <input
        className="field-input"
        value={query}
        placeholder={t("wizard.search")}
        onChange={(event) => onQuery(event.target.value)}
      />
      <p className="wizard-note">
        {query.trim()
          ? t("wizard.matchCount", { matched: matches.length, total: SOURCES.length })
          : t("wizard.sourceCount", { count: SOURCES.length })}
      </p>
      {/* Custom always survives a search, so this only shows when the query
          matched nothing else and the user may not have noticed it. */}
      {query.trim() && matches.length === 1 && (
        <p className="wizard-note">{t("wizard.noMatch")}</p>
      )}
      <div className="source-list">
        {matches.map((source) => (
          <button
            key={source.id}
            type="button"
            className="model-choice source-option"
            onClick={() => onChoose(source)}
          >
            <div className="model-choice-head">
              <span className="source-identity">
                <span className="source-name">{source.name}</span>
                <span className="mono faint truncate">
                  {source.baseUrl || t("wizard.hint.custom")}
                </span>
              </span>
              <span className="badge">{t(`wizard.kind.${source.kind}` as MessageKey)}</span>
            </div>
          </button>
        ))}
      </div>
    </>
  );
}

/** Step two: how to reach it. */
function ConnectionStep({
  source,
  displayName,
  baseUrl,
  model,
  apiKey,
  hasKey,
  onDisplayName,
  onBaseUrl,
  onModel,
  onApiKey
}: {
  source: Source;
  displayName: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  hasKey: boolean;
  onDisplayName: (value: string) => void;
  onBaseUrl: (value: string) => void;
  onModel: (value: string) => void;
  onApiKey: (value: string) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const keyRequired = needsApiKey(source);
  return (
    <>
      <p className="wizard-note">{t(KIND_HINT[source.kind])}</p>

      <label className="field-block">
        <span className="field-label">{t("wizard.displayName")}</span>
        <input
          className="field-input"
          value={displayName}
          placeholder={source.name}
          onChange={(event) => onDisplayName(event.target.value)}
        />
      </label>

      <label className="field-block">
        <span className="field-label">{t("wizard.protocol")}</span>
        {/*
          One option, shown rather than hidden: it is what the endpoint has to
          speak, and a form that omitted it would leave the user guessing why
          an endpoint that is not OpenAI-compatible fails.
        */}
        <select
          className="field-input"
          value={source.protocol}
          disabled
          aria-readonly="true"
        >
          <option value="openai_compatible">OpenAI-compatible</option>
        </select>
      </label>

      <label className="field-block">
        <span className="field-label">{t("settings.provider.baseUrl")}</span>
        <input
          className="field-input"
          value={baseUrl}
          placeholder="https://api.example.com/v1"
          onChange={(event) => onBaseUrl(event.target.value)}
        />
      </label>

      <label className="field-block">
        <span className="field-label">{t("settings.provider.model")}</span>
        <input
          className="field-input"
          value={model}
          placeholder={source.exampleModel || "model-name"}
          onChange={(event) => onModel(event.target.value)}
        />
      </label>

      {keyRequired && (
        <label className="field-block">
          <span className="field-label">
            {t("settings.provider.apiKey")}
            {hasKey && <span className="badge ok">{t("settings.provider.keySet")}</span>}
          </span>
          <input
            className="field-input"
            type="password"
            value={apiKey}
            placeholder={hasKey ? t("settings.provider.keyKept") : t("settings.provider.keyNew")}
            onChange={(event) => onApiKey(event.target.value)}
          />
        </label>
      )}
    </>
  );
}

/** Step three: what the runtime does with it. */
function ModelsStep({
  projectRoot,
  providers,
  saved
}: {
  projectRoot: string;
  providers: readonly Provider[];
  saved: boolean;
}): React.JSX.Element {
  const { t } = useI18n();
  const { roles, reload } = useProviders(projectRoot, true);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string>();

  const configured = providers.find((provider) => provider.id === "openai_compatible");
  const live = configured?.ready === true;

  const route = async (role: string, providerId: string): Promise<void> => {
    if (busy) return;
    setBusy(role);
    setFailure(undefined);
    try {
      await (providerId ? routeModelRole(projectRoot, role, providerId) : clearModelRole(projectRoot, role));
      reload();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("wizard.routeFailed")));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      {/*
        Said rather than worked around: Kura reads provider configuration at
        startup, so an endpoint saved a moment ago is not answering yet and its
        model list cannot be fetched. Pretending otherwise would mean an empty
        list that looks like a broken endpoint.
      */}
      {saved && <p className="wizard-note tone-ok">{t("settings.provider.restart")}</p>}
      {!live && <p className="wizard-note">{t("wizard.fetchHintManual")}</p>}

      <span className="field-label dialog-section">{t("wizard.roleRouting")}</span>
      <p className="wizard-note">{t("wizard.roleHint")}</p>
      <div className="source-list">
        {(roles ?? []).map((role) => (
          <div key={role.role} className="settings-row">
            <div className="row-label">
              <span>{t(`role.${role.role}` as MessageKey)}</span>
              <small>{role.provider_id || t("wizard.roleUnrouted")}</small>
            </div>
            <div className="card-actions">
              {role.routed ? (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void route(role.role, "")}
                  disabled={busy !== null}
                >
                  {t("wizard.roleClear")}
                </button>
              ) : (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void route(role.role, "openai_compatible")}
                  disabled={busy !== null || !live}
                >
                  {busy === role.role ? t("wizard.routing") : t("wizard.roleUse")}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      {failure && <p className="wizard-note tone-bad">{failure}</p>}
    </>
  );
}
