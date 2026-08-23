import React, { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  type Provider,
  type ProviderAuth,
  clearModelRole,
  type ProviderProbe,
  probeProvider,
  providerAuth,
  providerAuthAction,
  forgetProviderSettings,
  routeModelRole,
  saveProviderSettings,
  useProviderSettings,
  useProviders
} from "../providers";
import {
  type Source,
  isAccountSource,
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
  account: "wizard.hint.account",
  cloud: "wizard.hint.cloud",
  local: "wizard.hint.local",
  custom: "wizard.hint.custom"
};

/**
 * Spelled out rather than interpolated, for the third time in this codebase.
 * `t(\`wizard.kind.${kind}\` as MessageKey)` compiles and then fails at render
 * with a missing key -- the cast removes exactly the check that would have
 * caught adding a kind without its label.
 */
const KIND_BADGE: Record<Source["kind"], MessageKey> = {
  account: "wizard.kind.account",
  cloud: "wizard.kind.cloud",
  local: "wizard.kind.local",
  custom: "wizard.kind.custom"
};

/** The core's five modalities, each with its own label for the same reason. */
const ROLE_LABEL: Record<string, MessageKey> = {
  primary: "route.primary",
  vision: "route.vision",
  image: "route.image",
  video: "route.video",
  embed: "route.embed"
};

const AUTH_BADGE: Record<string, MessageKey> = {
  authenticated: "wizard.badge.done",
  pending_login: "wizard.badge.waiting",
  login_required: "wizard.badge.idle",
  revoked: "wizard.badge.idle",
  unknown: "wizard.badge.idle",
  error: "wizard.badge.idle"
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

          {step === "connection" && source && isAccountSource(source) && (
            <AccountStep source={source} projectRoot={projectRoot} />
          )}

          {step === "connection" && source && !isAccountSource(source) && (
            <ConnectionStep
              source={source}
              projectRoot={projectRoot}
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
            {step === "connection" && source && isAccountSource(source) && (
              <button
                type="button"
                className="primary-button"
                onClick={() => setStep("models")}
              >
                {t("wizard.next")}
              </button>
            )}
            {step === "connection" && source && !isAccountSource(source) && (
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
              <span className="badge">{t(KIND_BADGE[source.kind])}</span>
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
  projectRoot,
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
  projectRoot: string;
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
  const [probe, setProbe] = useState<ProviderProbe | null>(null);
  const [probing, setProbing] = useState(false);

  const fetchModels = async (): Promise<void> => {
    if (probing || !baseUrl.trim() || !isDesktopRuntime()) return;
    setProbing(true);
    setProbe(null);
    try {
      setProbe(await probeProvider(projectRoot, baseUrl, apiKey));
    } catch (error: unknown) {
      setProbe({
        schema_version: "loopforge-provider-probe-v1",
        reachable: false,
        models: [],
        error: errorMessage(error, t("wizard.probeFailed"))
      });
    } finally {
      setProbing(false);
    }
  };

  /** A 401 means the key; anything else reached means the endpoint. */
  const failureHint = (): string => {
    if (!probe || probe.reachable) return "";
    if (probe.status === 401 || probe.status === 403) return t("wizard.probeBadKey");
    if (probe.status) return t("wizard.probeBadUrl", { status: probe.status });
    return probe.error || t("wizard.probeFailed");
  };
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

      {/*
        The key sits above the model because fetching the list needs it, and a
        form that asked for the model first would be asking the user to know
        something the endpoint can just tell them.
      */}
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

      <label className="field-block">
        <span className="field-label">
          {t("settings.provider.model")}
          {probe?.reachable && (
            <span className="badge ok">
              {t("wizard.fetched", { count: probe.models.length })}
            </span>
          )}
        </span>
        {/*
          A list and a text field at once: the endpoint knows its catalogue,
          but a vendor can serve a model it does not list, so typing one stays
          possible.
        */}
        <input
          className="field-input"
          value={model}
          list="provider-models"
          placeholder={source.exampleModel || "model-name"}
          onChange={(event) => onModel(event.target.value)}
        />
        <datalist id="provider-models">
          {(probe?.models ?? []).map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>

      <div className="card-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={() => void fetchModels()}
          disabled={probing || !baseUrl.trim()}
        >
          {probing ? t("wizard.probing") : t("wizard.fetch")}
        </button>
      </div>
      {probe && !probe.reachable && (
        <p className="wizard-note tone-bad">{failureHint()}</p>
      )}
      {probe?.reachable && probe.models.length === 0 && (
        <p className="wizard-note">{t("wizard.fetchHintManual")}</p>
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
              <span>{ROLE_LABEL[role.role] ? t(ROLE_LABEL[role.role]) : role.role}</span>
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

/**
 * Connecting a subscription account.
 *
 * Nothing here signs the user in. A managed provider borrows a command-line
 * tool they have already authenticated -- the runtime can see whether that
 * tool exists and whether it is signed in, and it hands back the command to
 * run, but running it belongs to the user and their own account. So this shows
 * the state, shows the command, and offers to re-check.
 */
function AccountStep({
  source,
  projectRoot
}: {
  source: Source;
  projectRoot: string;
}): React.JSX.Element {
  const { t } = useI18n();
  const [auth, setAuth] = useState<ProviderAuth | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  const providerId = source.providerId ?? source.id;

  const load = React.useCallback(async () => {
    try {
      setAuth(await providerAuth(projectRoot, providerId));
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("wizard.authFailed")));
    }
  }, [projectRoot, providerId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (action: "start" | "complete" | "refresh" | "revoke"): Promise<void> => {
    if (busy || !isDesktopRuntime()) return;
    setBusy(true);
    setFailure(undefined);
    try {
      setAuth(await providerAuthAction(projectRoot, providerId, action));
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("wizard.authFailed")));
    } finally {
      setBusy(false);
    }
  };

  const status = auth?.status ?? "unknown";
  const signedIn = status === "authenticated";
  const command = (auth?.login_command ?? []).join(" ");

  return (
    <>
      <p className="wizard-note">{t("wizard.hint.account")}</p>

      <div className="settings-row">
        <div className="row-label">
          <span>{source.name}</span>
          <small>
            {signedIn && auth?.account_label
              ? [auth.account_label, auth.plan].filter(Boolean).join(" · ")
              : auth?.checked === false
                ? t("wizard.authUnchecked")
                : t("wizard.authCliMissing")}
          </small>
        </div>
        <span className={`badge ${signedIn ? "ok" : ""}`}>
          {t(AUTH_BADGE[status] ?? "wizard.badge.idle")}
        </span>
      </div>

      {/*
        Stated before anything else is offered: without the tool installed
        there is no sign-in to attempt, and a button that opened nothing would
        be the worst possible answer.
      */}
      {auth?.checked && !auth.cli_available && (
        <p className="wizard-note tone-bad">{t("wizard.authCliMissing")}</p>
      )}

      {auth?.cli_available && !signedIn && command && (
        <>
          <p className="wizard-note">{t("wizard.authRunCommand")}</p>
          <pre className="run-stream">{command}</pre>
        </>
      )}

      {signedIn && auth?.models && auth.models.length > 0 && (
        <p className="wizard-note">
          {t("wizard.acctModels")}: {auth.models.length}
        </p>
      )}

      <div className="card-actions dialog-section">
        <button
          type="button"
          className="secondary-button"
          onClick={() => void act("refresh")}
          disabled={busy}
        >
          {busy ? t("wizard.authChecking") : t("wizard.authCheck")}
        </button>
        {auth?.cli_available && !signedIn && (
          <>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void act("start")}
              disabled={busy}
            >
              {t("wizard.signIn")}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void act("complete")}
              disabled={busy}
            >
              {t("wizard.confirmed")}
            </button>
          </>
        )}
        {signedIn && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => void act("revoke")}
            disabled={busy}
          >
            {t("wizard.signOut")}
          </button>
        )}
      </div>

      {auth?.last_error && <p className="wizard-note tone-bad">{auth.last_error}</p>}
      {failure && <p className="wizard-note tone-bad">{failure}</p>}
    </>
  );
}
