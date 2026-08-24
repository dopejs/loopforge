import React, { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  type Account,
  beginSignIn,
  completeSignIn,
  openExternal,
  signOut,
  useAccounts
} from "../accounts";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  type Provider,
  clearModelRole,
  type ProviderProbe,
  probeProvider,
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
 * Spelled out rather than interpolated, for the third time in this codebase.
 * `t(\`wizard.kind.${kind}\` as MessageKey)` compiles and then fails at render
 * with a missing key -- the cast removes exactly the check that would have
 * caught adding a kind without its label.
 */
const KIND_BADGE: Record<Source["kind"], MessageKey> = {
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
  projectRoot,
  onClose,
  onSaved
}: {
  projectRoot: string;
  onClose: () => void;
  onSaved?: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  // The live inventory, not a snapshot taken when the dialog opened. It is
  // what says whether the provider being configured already has a credential,
  // and after a save it is what says the save took.
  const { providers, reload: reloadProviders } = useProviders(projectRoot, true);

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

  /*
   * The wizard starts where it says it starts.
   *
   * It used to read one global "provider settings" record and, if anything had
   * ever been configured, jump straight to step two on that record's source --
   * so opening "Add Provider" a second time skipped the list of sources
   * entirely and presented the previous provider's endpoint with an API-key
   * field, whatever the user had actually picked. There is more than one
   * provider now; there is no "the" configured one to reopen on.
   */

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
    setModel(picked.exampleModel ?? "");
    setApiKey("");
    // Already signed into this vendor: use that, rather than presenting an
    // API-key field to someone who has a subscription and asking them to pick
    // the account out of a segmented control they have to notice first.
    const signedIn = accounts.find(
      (candidate) => candidate.id === picked.oauthProviderId && candidate.signed_in
    );
    setOauthProviderId(signedIn ? signedIn.id : "");
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
    // An account brings its own endpoint, wire and credential. Probing with
    // the key field -- empty, because the account supplies it -- and against
    // the OpenAI shape, which this vendor does not serve, produced a 401 about
    // a key the user never typed.
    const account = oauthProviderId ? vendorAccount : null;
    const endpoint = account?.api_base_url || baseUrl;
    const protocol = account?.protocol || "openai_compatible";
    setBusy(true);
    setFailure(undefined);
    try {
      const found = await probeProvider(
        projectRoot,
        endpoint,
        apiKey,
        protocol,
        oauthProviderId
      );
      setModels(found.reachable ? found.models : []);
      if (!found.reachable && found.status === 401) {
        setFailure(t("wizard.probeBadKey"));
        return;
      }
    } catch {
      // A catalogue is a convenience. A vendor that does not publish one still
      // works when the user names a model, so the step advances either way.
      setModels(account?.default_model ? [account.default_model] : []);
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
        // The account's endpoint wins where one supplies the credential: the
        // preset's URL is the API-key one, which is not always the same.
        base_url:
          (oauthProviderId && vendorAccount?.api_base_url) || baseUrl,
        api_key: apiKey,
        model,
        display_name: displayName,
        protocol: vendorAccount?.protocol || source.protocol,
        oauth_provider_id: oauthProviderId,
        // Named after the source, so a second provider is a second provider.
        provider_id: oauthProviderId || source.id
      });
      setApiKey("");
      setSaved(true);
      // Both inventories: the one this dialog reads to enable role routing,
      // and the one the settings page behind it lists. Saying "saved" while
      // the list behind the dialog still showed nothing is what made a
      // successful save look like it had done nothing at all.
      reloadProviders();
      onSaved?.();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("settings.provider.saveFailed")));
    } finally {
      setBusy(false);
    }
  };

  /** The provider this run of the wizard is configuring, once it exists. */
  const providerId = oauthProviderId || source?.id || "";
  const existing = providers.find((candidate) => candidate.id === providerId) ?? null;
  // Whether *this* provider already holds a credential -- not whether any
  // provider anywhere does, which is what the single settings record answered
  // and why an untouched vendor could show "key set".
  const hasKey = existing?.secret_configured === true;
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

          {step === "connection" && source && (
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
              providerId={providerId}
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
            {step === "connection" && hasKey && providerId && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  void forgetProviderSettings(projectRoot, providerId).then(() => {
                    reloadProviders();
                    onSaved?.();
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
            {step === "connection" && source && (
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
            {step === "models" && !saved && (
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
            {/*
              A saved provider is done. The dialog used to stay open with a
              "saved" line and a Save button that saved the same thing again,
              leaving the user to guess whether anything had happened -- the
              provider list is behind this dialog, so the only way to find out
              was to close it.
            */}
            {step === "models" && saved && (
              <button type="button" className="primary-button" onClick={onClose}>
                {t("wizard.done")}
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

  async function leave(): Promise<void> {
    setBusy(true);
    setFailure("");
    try {
      await signOut(projectRoot, account.id);
      onSignedIn();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("account.failed")));
    } finally {
      setBusy(false);
    }
  }

  if (account.signed_in) {
    return (
      <>
        <p className="field-static">
          <span className="badge ok">{t("account.signedIn")}</span>{" "}
          {account.account_label || account.name}
        </p>
        {/*
          A way back out. A grant can be refused later -- these expire outright
          about a month after the interactive login -- and without this the
          only recovery was to sign in again somewhere that no longer exists.
        */}
        <button type="button" className="ghost-button small" disabled={busy} onClick={leave}>
          {t("account.signOut")}
        </button>
        <small className="field-hint">{t("wizard.accountCredential")}</small>
        <small className="field-hint">{t("account.localOnly")}</small>
        {failure && <p className="settings-note issue-line">{failure}</p>}
      </>
    );
  }

  async function start(): Promise<void> {
    setFailure("");
    setBusy(true);
    try {
      const started = await beginSignIn(projectRoot, account.id);
      setPending({ url: started.url, user_code: started.user_code });
      // Failure to launch is not fatal, but it must be visible: the URL is
      // shown either way, so a shell that cannot open a browser leaves the
      // user with something to click rather than a wait that never ends.
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
          <a href={pending.url} target="_blank" rel="noreferrer" className="mono">
            {t("account.openPage")}
          </a>
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

      {/*
        A preset carries its own protocol, so there is nothing to choose. The
        field was a select with one option, permanently disabled -- it asked
        the user to confirm something they had already decided by picking the
        preset. A custom endpoint has the same single option today, so it is
        stated in the hint above rather than dressed up as a choice.
      */}

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
  providerId,
  saved,
  models,
  model,
  exampleModel,
  onModel
}: {
  projectRoot: string;
  /** The provider being configured, which is what these roles point at. */
  providerId: string;
  saved: boolean;
  models: readonly string[];
  model: string;
  exampleModel: string;
  onModel: (value: string) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const { providers, roles, reload } = useProviders(projectRoot, true);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string>();

  // Re-read once the save lands: until then this provider is not in the
  // inventory, so nothing can be routed at it.
  useEffect(() => {
    if (saved) reload();
  }, [saved, reload]);

  /*
   * The provider this wizard is adding -- by its own id.
   *
   * Both of these were the literal string `openai_compatible`: the readiness
   * check looked up a provider the user had not chosen, so every "use this
   * provider" button stayed disabled, and routing sent the role to that same
   * fixed id, which would have pointed a modality at the wrong endpoint had
   * the button ever been clickable.
   */
  const configured = providers.find((provider) => provider.id === providerId);
  const live = configured?.ready === true;

  const route = async (role: string, target: string): Promise<void> => {
    if (busy) return;
    setBusy(role);
    setFailure(undefined);
    try {
      await (target
        ? routeModelRole(projectRoot, role, target, model.trim())
        : clearModelRole(projectRoot, role));
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

      {/* Live on the next request; nothing to restart and nothing in flight
          was ended to get there. */}
      {saved && <p className="wizard-note tone-ok">{t("settings.provider.live")}</p>}

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
              {/*
                A role already pointed somewhere else offers the swap as well
                as the clear. Only "clear" was offered, so changing which
                provider answered a modality meant unrouting it, closing the
                dialog, and coming back -- and with a single slot it was not
                even a different provider to swap to.
              */}
              {role.routed && role.provider_id !== providerId && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void route(role.role, providerId)}
                  disabled={busy !== null || !live}
                >
                  {busy === role.role ? t("wizard.routing") : t("wizard.roleUse")}
                </button>
              )}
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
                  onClick={() => void route(role.role, providerId)}
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

