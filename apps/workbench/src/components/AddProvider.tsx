import React, { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  type Account,
  beginSignIn,
  completeSignIn,
  openExternal,
  useAccounts
} from "../accounts";
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
  const [oauthProviderId, setOauthProviderId] = useState("");
  // The catalogue the endpoint reported, lifted here because it is fetched
  // with the credential in step two and chosen from in step three.
  const [models, setModels] = useState<readonly string[]>([]);
  const { accounts, reload: reloadAccounts } = useAccounts(projectRoot, true);
  // The account belonging to the chosen vendor, or none. A preset without one
  // simply has no sign-in to offer.
  const vendorAccount =
    accounts.find((candidate) => candidate.id === source?.oauthProviderId) ?? null;
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

  /**
   * Leave the connection step, asking the endpoint what it serves on the way.
   *
   * A failure here is not fatal: the catalogue is a convenience, and a vendor
   * that does not list its models still works if the user names one. So the
   * step advances either way and the next one says which happened.
   */
  const advance = async (): Promise<void> => {
    if (busy || !source || !isDesktopRuntime()) return;
    setBusy(true);
    setFailure(undefined);
    try {
      const found = await probeProvider(projectRoot, baseUrl, apiKey);
      setModels(found.reachable ? found.models : []);
      if (!found.reachable && found.status === 401) {
        setFailure(t("wizard.probeBadKey"));
        return;
      }
    } catch {
      setModels([]);
    } finally {
      setBusy(false);
    }
    setStep("models");
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
        protocol: source.protocol,
        oauth_provider_id: oauthProviderId
      });
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
  const keyRequired = source ? needsApiKey(source) : true;
  /** A credential of some kind: a key, a stored key, or a signed-in account. */
  const hasCredential = Boolean(
    !keyRequired || oauthProviderId || apiKey || hasKey
  );
  const canSave = Boolean(
    baseUrl.trim() &&
      model.trim() &&
      // An account is a credential: requiring a typed key as well would make
      // the one option that stays current impossible to choose.
      (!keyRequired || oauthProviderId || apiKey || hasKey)
  );

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
              oauthProviderId={oauthProviderId}
              vendorAccount={vendorAccount}
              onAccountsChanged={reloadAccounts}
              onDisplayName={setDisplayName}
              onBaseUrl={setBaseUrl}
              onModel={setModel}
              onApiKey={setApiKey}
              onOauthProviderId={setOauthProviderId}
            />
          )}

          {step === "models" && (
            <ModelsStep
              projectRoot={projectRoot}
              providers={providers}
              saved={saved}
              models={models}
              model={model}
              exampleModel={source?.exampleModel ?? ""}
              onModel={setModel}
            />
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
                // Advances rather than saves: the model has not been chosen
                // yet, and saving before it would write a configuration the
                // next step is about to complete.
                onClick={() => void advance()}
                disabled={busy || !hasCredential}
              >
                {busy ? t("wizard.probing") : t("wizard.next")}
              </button>
            )}
            {step === "models" && (
              <button
                type="button"
                className="primary-button"
                onClick={() => void save()}
                // Not disabled on validity alone: the Agent decides whether an
                // endpoint is acceptable, and its refusal names the reason.
                disabled={busy || !canSave}
              >
                {busy ? t("settings.provider.saving") : t("wizard.save")}
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
/**
 * Signing a vendor's subscription in from inside the wizard.
 *
 * The account is a credential for the endpoint being configured, so it is
 * established here. Making the user leave for the usage panel and come back
 * inverted the relationship: usage is where you go to see what an account has
 * spent, not where you go to create one.
 */
function AccountCredential({
  account,
  projectRoot,
  onSignedIn
}: {
  account: Account;
  projectRoot: string;
  onSignedIn: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [pending, setPending] = useState<{ url: string; user_code: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  if (account.signed_in) {
    return (
      <>
        <p className="field-static">
          <span className="badge ok">{t("account.signedIn")}</span>{" "}
          {account.account_label || account.name}
        </p>
        <small className="field-hint">{t("wizard.accountCredential")}</small>
      </>
    );
  }

  async function start(): Promise<void> {
    setFailure("");
    setBusy(true);
    try {
      const started = await beginSignIn(projectRoot, account.id);
      setPending({ url: started.url, user_code: started.user_code });
      void openExternal(started.url).catch(() => {});
      await completeSignIn(projectRoot, account.id);
      setPending(null);
      onSignedIn();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("account.failed")));
      setPending(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {account.configured === false ? (
        <small className="field-hint">{t("wizard.accountUnavailable")}</small>
      ) : (
        <button
          type="button"
          className="primary-button small"
          disabled={busy}
          onClick={start}
        >
          {t("account.signIn")}
        </button>
      )}
      {pending && (
        <div className="account-pending">
          {pending.user_code ? (
            <>
              <span>{t("account.enterCode")}</span>
              <code className="device-code">{pending.user_code}</code>
            </>
          ) : (
            <span>{t("account.waiting")}</span>
          )}
        </div>
      )}
      {failure && <p className="settings-note issue-line">{failure}</p>}
    </>
  );
}

function ConnectionStep({
  source,
  projectRoot,
  displayName,
  baseUrl,
  model,
  apiKey,
  hasKey,
  oauthProviderId,
  vendorAccount,
  onAccountsChanged,
  onDisplayName,
  onBaseUrl,
  onModel,
  onApiKey,
  onOauthProviderId
}: {
  source: Source;
  projectRoot: string;
  displayName: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  hasKey: boolean;
  oauthProviderId: string;
  /** The account this vendor offers, if it offers one at all. */
  vendorAccount: Account | null;
  onAccountsChanged: () => void;
  onDisplayName: (value: string) => void;
  onBaseUrl: (value: string) => void;
  onModel: (value: string) => void;
  onApiKey: (value: string) => void;
  onOauthProviderId: (value: string) => void;
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

      {/*
        A chosen preset already carries its endpoint. Presenting it as a field
        to fill in asks the user for something they picked the preset to avoid
        having to know; it is shown so they can see where their key is going,
        and only a custom source has anything to type.
      */}
      <label className="field-block">
        <span className="field-label">{t("settings.provider.baseUrl")}</span>
        {source.kind === "custom" ? (
          <input
            className="field-input"
            value={baseUrl}
            placeholder="https://api.example.com/v1"
            onChange={(event) => onBaseUrl(event.target.value)}
          />
        ) : (
          <output className="field-static mono">{baseUrl}</output>
        )}
      </label>

      {/*
        The key sits above the model because fetching the list needs it, and a
        form that asked for the model first would be asking the user to know
        something the endpoint can just tell them.
      */}
      {keyRequired && (
        <fieldset className="field-block">
          <legend className="field-label">{t("settings.provider.apiKey")}</legend>
          {/*
            A signed-in account is offered alongside a typed key rather than
            instead of it: an OAuth token expires in about an hour, so an
            account is the only credential that can be kept current without
            the user retyping one, but plenty of endpoints only take a key.
          */}
          {/*
            Only vendors that actually offer a subscription sign-in get this
            choice. A disabled toggle on every preset told the user that an
            account might exist for endpoints that have none, which is noise
            at best and misleading at worst.
          */}
          {vendorAccount && (
            <div className="segmented">
              <button
                type="button"
                className={oauthProviderId ? "" : "active"}
                onClick={() => onOauthProviderId("")}
              >
                {t("wizard.useKey")}
              </button>
              <button
                type="button"
                className={oauthProviderId ? "active" : ""}
                onClick={() => onOauthProviderId(vendorAccount.id)}
              >
                {t("wizard.useAccount")}
              </button>
            </div>
          )}

          {oauthProviderId && vendorAccount ? (
            /*
              Signed in here, not somewhere else. Sending the user to the usage
              panel to sign in and then back again to finish configuring is the
              wrong way round: the account is a credential for this endpoint,
              and usage is where you go to see what it has spent.
            */
            <AccountCredential
              account={vendorAccount}
              projectRoot={projectRoot}
              onSignedIn={onAccountsChanged}
            />
          ) : (
            <>
              <input
                className="field-input"
                type="password"
                value={apiKey}
                aria-label={t("settings.provider.apiKey")}
                placeholder={
                  hasKey ? t("settings.provider.keyKept") : t("settings.provider.keyNew")
                }
                onChange={(event) => onApiKey(event.target.value)}
              />
              {hasKey && <span className="badge ok">{t("settings.provider.keySet")}</span>}

            </>
          )}
        </fieldset>
      )}

      {/*
        The model is chosen in step three, not here. Asking for it alongside
        the credential meant asking the user to name a model before anything
        had been able to ask the endpoint what it serves -- and the wizard
        already has a step whose whole purpose is that choice.
      */}
    </>
  );
}

/** Step three: what the runtime does with it. */
function ModelsStep({
  projectRoot,
  providers,
  saved,
  models,
  model,
  exampleModel,
  onModel
}: {
  projectRoot: string;
  providers: readonly Provider[];
  saved: boolean;
  models: readonly string[];
  model: string;
  exampleModel: string;
  onModel: (value: string) => void;
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
      {/*
        The choice this step is named for. The catalogue was fetched with the
        credential in the previous step, so by here it either exists or the
        endpoint does not publish one -- and typing a name stays possible
        either way, because a vendor can serve a model it does not list.
      */}
      <label className="field-block">
        <span className="field-label">{t("settings.provider.model")}</span>
        <input
          className="field-input"
          value={model}
          list="provider-models"
          placeholder={exampleModel || "model-name"}
          onChange={(event) => onModel(event.target.value)}
        />
        <datalist id="provider-models">
          {models.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <small className="field-hint">
          {models.length > 0 ? t("wizard.pickModel") : t("wizard.noModelList")}
        </small>
      </label>

      {saved && <p className="wizard-note tone-ok">{t("settings.provider.restart")}</p>}

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
