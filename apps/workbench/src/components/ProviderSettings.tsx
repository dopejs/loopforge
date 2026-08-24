import React, { useState } from "react";
import { useI18n } from "../i18n";
import { Icon } from "../icons";
import { useKey } from "./primitives";
import { errorMessage } from "../daemon";
import {
  forgetProviderSettings,
  type ModelRole,
  type Provider,
  useProviders
} from "../providers";
import { AddProvider } from "./AddProvider";
import type { MessageKey } from "../i18n/locales/en";

function ProviderDetail({
  provider,
  projectRoot,
  onBack,
  onRemoved
}: {
  provider: Provider;
  projectRoot: string;
  onBack: () => void;
  onRemoved: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();
  const [removing, setRemoving] = useState(false);
  const [failure, setFailure] = useState<string>();

  /*
   * Removing one. There was no way to: the only delete deleted a fixed
   * `openai_compatible` row whatever the user was looking at, so a provider
   * added under its own name could not be taken away again -- and a stale one
   * stayed in the list and in the routing table indefinitely.
   */
  const remove = async (): Promise<void> => {
    if (removing) return;
    setRemoving(true);
    setFailure(undefined);
    try {
      await forgetProviderSettings(projectRoot, provider.id);
      onRemoved();
      onBack();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("provider.removeFailed")));
    } finally {
      setRemoving(false);
    }
  };

  /*
   * Only fields `loopforge-provider-v1` actually carries are rendered. Budgets,
   * custom headers and sampling knobs were in the design mock but are not Kura
   * provider fields — showing them would imply Loopforge-side provider state.
   */
  const connection: { label: string; value: string }[] = [];
  if (provider.base_url) connection.push({ label: "baseUrl", value: provider.base_url });
  connection.push({
    label: "apiKey",
    value: provider.secret_configured ? t("provider.secretSet") : t("provider.secretUnset")
  });
  if (provider.account_label)
    connection.push({ label: "account", value: provider.account_label });
  if (provider.plan) connection.push({ label: "plan", value: provider.plan });

  const runtime: { label: string; value: string }[] = [];
  if (provider.timeout_ms !== undefined)
    runtime.push({ label: "timeout", value: `${provider.timeout_ms} ms` });
  if (provider.max_retries !== undefined)
    runtime.push({ label: "retries", value: String(provider.max_retries) });
  if (provider.default_model)
    runtime.push({ label: "defaultModel", value: provider.default_model });

  return (
    <>
      <button type="button" className="back-link" onClick={onBack}>
        ‹ {t("settings.group.provider")}
      </button>

      <div className="settings-intro">
        <h2>
          {provider.title}
          <span className={`badge ${provider.health === "ready" ? "ok" : provider.health === "error" ? "bad" : ""}`}>
            {key("provider.status", provider.health)}
          </span>
        </h2>
        <p>
          {provider.family}
          {provider.base_url ? ` · ${provider.base_url}` : ""}
        </p>
      </div>

      {provider.issues && provider.issues.length > 0 && (
        <div className="settings-card issue-card">
          {provider.issues.map((issue) => (
            <p key={issue} className="issue-line">
              {issue}
            </p>
          ))}
        </div>
      )}

      <div className="settings-section">
        <span className="section-title">{t("provider.connection")}</span>
      </div>
      <div className="settings-card">
        {connection.map((field) => (
          <div key={field.label} className="settings-row">
            <div className="row-label">
              <span>{key("provider.field", field.label)}</span>
            </div>
            <span className="mono dim truncate flex-value">{field.value}</span>
          </div>
        ))}
      </div>

      {runtime.length > 0 && (
        <>
          <div className="settings-section">
            <span className="section-title">{t("provider.runtime")}</span>
          </div>
          <div className="settings-card">
            {runtime.map((field) => (
              <div key={field.label} className="settings-row">
                <div className="row-label">
                  <span>{key("provider.row", field.label)}</span>
                </div>
                <span className="mono dim">{field.value}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="settings-section">
        <span className="section-title">
          {t("provider.models", { count: provider.models.length })}
        </span>
      </div>
      <div className="settings-card">
        {provider.models.map((model) => (
          <div key={model.id} className="model-row">
            <div className="model-head">
              <span className="mono truncate">{model.display_name}</span>
              {model.is_default && <span className="badge accent">{t("provider.default")}</span>}
              {!model.available && <span className="badge">{t("provider.modelUnavailable")}</span>}
            </div>
            <div className="model-meta">
              <span className="caps">
                {model.capabilities.map((cap) => (
                  <span key={cap} className="cap">
                    {cap}
                  </span>
                ))}
              </span>
            </div>
          </div>
        ))}
        {provider.models.length === 0 && (
          <p className="settings-empty">{t("provider.noModels")}</p>
        )}
      </div>

      <div className="settings-section">
        <span className="section-title">{t("provider.remove")}</span>
      </div>
      <div className="settings-card">
        <div className="settings-row">
          <div className="row-label">
            <span>{t("provider.remove")}</span>
            <small>{t("provider.removeHint")}</small>
          </div>
          <button
            type="button"
            className="secondary-button"
            disabled={removing}
            onClick={() => void remove()}
          >
            {removing ? t("provider.removing") : t("provider.remove")}
          </button>
        </div>
        {failure && <p className="issue-line">{failure}</p>}
      </div>
    </>
  );
}

/** `provider · model`, or just the provider when it uses its default model. */
function describeRoute(route: ModelRole): string {
  return route.model ? `${route.provider_id} · ${route.model}` : route.provider_id;
}

/**
 * Role labels, spelled out.
 *
 * These went through a casting helper before, and three of the five roles had
 * no label at all -- they rendered as empty rows and nothing reported it. A
 * literal key makes a missing one a build error.
 */
const ROLE_LABEL: Record<string, MessageKey> = {
  primary: "route.primary",
  vision: "route.vision",
  image: "route.image",
  video: "route.video",
  embed: "route.embed"
};

const ROLE_HINT: Record<string, MessageKey> = {
  primary: "route.primaryHint",
  vision: "route.visionHint",
  image: "route.imageHint",
  video: "route.videoHint",
  embed: "route.embedHint"
};

export function ProviderSettings({
  projectRoot
}: {
  projectRoot: string;
}): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const { providers, roles, reason, loading, reload } = useProviders(projectRoot, true);

  const selected = providers.find((candidate) => candidate.id === selectedId) ?? null;
  if (selected) {
    return (
      <ProviderDetail
        provider={selected}
        projectRoot={projectRoot}
        onBack={() => setSelectedId(null)}
        onRemoved={reload}
      />
    );
  }

  return (
    <>
      <div className="settings-section">
        <span className="section-title">
          {t("provider.count", { count: providers.length })}
        </span>
        <button type="button" className="primary-button small" onClick={() => setAdding(true)}>
          {t("provider.add")}
        </button>
      </div>

      {providers.length === 0 ? (
        <p className="settings-note">
          {loading ? t("provider.loading") : reason ? t("provider.unavailable") : t("provider.none")}
        </p>
      ) : (
        <div className="settings-card">
          {providers.map((provider) => (
            <button
              key={provider.id}
              type="button"
              className="provider-row"
              onClick={() => setSelectedId(provider.id)}
            >
              <span className={`state-dot ${provider.health === "ready" ? "ok" : provider.health === "error" ? "bad" : "off"}`} aria-hidden="true" />
              <span className="provider-identity">
                <span className="provider-name">
                  {provider.title}
                  {provider.family && <span className="tag">{provider.family}</span>}
                </span>
                {provider.base_url && (
                  <span className="mono faint truncate">{provider.base_url}</span>
                )}
              </span>
              <span className="provider-status">
                <span className={`mono tone-${provider.health === "ready" ? "ok" : provider.health === "error" ? "bad" : "faint"}`}>
                  {key("provider.status", provider.health)}
                </span>
                <span className="mono faint">
                  {t("provider.modelCount", { count: provider.models.length })}
                </span>
              </span>
              <span className="chevron-end" aria-hidden="true">
                <Icon name="chevron" size={13} />
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="settings-section">
        <span className="section-title">{t("provider.routing")}</span>
      </div>
      {roles === undefined ? (
        // No role endpoint at all is a different state from "nothing routed",
        // and showing an empty table would misreport it.
        <p className="settings-note">{t("provider.routingUnsupported")}</p>
      ) : (
        <div className="settings-card">
          {roles.map((route) => (
            <div key={route.role} className="settings-row">
              <div className="row-label route-scene">
                <span>{ROLE_LABEL[route.role] ? t(ROLE_LABEL[route.role]) : route.role}</span>
                <small>{ROLE_HINT[route.role] ? t(ROLE_HINT[route.role]) : ""}</small>
              </div>
              <div className="route-model">
                {route.routed ? (
                  <span className="mono chip">{describeRoute(route)}</span>
                ) : (
                  <span className="mono faint">{t("provider.unassigned")}</span>
                )}
              </div>
              {route.routed && (
                <span className="mono faint route-source">
                  {key("provider.roleSource", route.source)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Owned here so a save can refresh the list it just changed. */}
      {adding && (
        <AddProvider
          projectRoot={projectRoot}
          onClose={() => setAdding(false)}
          onSaved={reload}
        />
      )}
    </>
  );
}
