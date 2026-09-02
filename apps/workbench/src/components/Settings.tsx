import React, { useState } from "react";
import { useI18n } from "../i18n";
import { LOCALES, LOCALE_NAMES } from "../i18n/locale";
import type { LocalePreference } from "../i18n";
import {
  ACCENTS,
  type Appearance,
  type Density,
  type ThemePreference,
  accentColor
} from "../appearance";
import { isConfigured, saveOperator, useOperator } from "../operator";
import { SHORTCUTS, displayShortcut, isApplePlatform } from "../shortcuts";
import { ProviderSettings } from "./ProviderSettings";
import { UsagePanel } from "./UsagePanel";
import { savePermissionMode, usePermissions } from "../approvals";
import { errorMessage } from "../daemon";
import { TOOL_CHIPS } from "../fixtures.providers";
import { PreviewBanner } from "./primitives";
import darkWordmark from "../assets/loopforge-horizontal-dark.svg";
import lightWordmark from "../assets/loopforge-horizontal-light.svg";
import { startWindowDrag } from "../window";
import type { MessageKey } from "../i18n/locales/en";

const GROUPS = [
  "general",
  "appearance",
  "language",
  "provider",
  "usage",
  "permissions",
  "shortcuts",
  "about"
] as const;

export type SettingsGroup = (typeof GROUPS)[number];

function Row({
  label,
  hint,
  children
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="settings-row">
      <div className="row-label">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </div>
      <div className="row-control">{children}</div>
    </div>
  );
}

/** A row that is designed but not yet backed by the Agent. */
function PreviewRow({
  label,
  hint,
  value,
  marker
}: {
  label: string;
  hint: string;
  value: React.ReactNode;
  marker: string;
}): React.JSX.Element {
  return (
    <Row label={label} hint={hint}>
      <span className="preview-value">
        <span className="preview-dot" title={marker} aria-label={marker} />
        {value}
      </span>
    </Row>
  );
}

function Toggle({
  checked,
  label,
  onChange
}: {
  checked: boolean;
  label: string;
  onChange: (next: boolean) => void;
}): React.JSX.Element {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={checked ? "toggle on" : "toggle"}
      onClick={() => onChange(!checked)}
    >
      <span className="toggle-knob" aria-hidden="true" />
    </button>
  );
}

function Segmented<T extends string>({
  value,
  options,
  label,
  onChange
}: {
  value: T;
  options: readonly { id: T; label: string }[];
  label: string;
  onChange: (next: T) => void;
}): React.JSX.Element {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="radio"
          aria-checked={option.id === value}
          className={option.id === value ? "segment active" : "segment"}
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/**
 * How much the agent may do without asking.
 *
 * The choices come from the runtime rather than being listed here: a list
 * maintained in the interface is a list that eventually describes an older
 * build, and this one decides whether a person is asked before their project
 * moves.
 */
function PermissionSettings({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { permissions, reason, reload } = usePermissions(projectRoot, true);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();

  const choose = async (mode: string): Promise<void> => {
    if (busy || mode === permissions?.mode) return;
    setBusy(true);
    setFailure(undefined);
    try {
      await savePermissionMode(projectRoot, mode);
      reload();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("approval.failed")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("permission.title")}</span>
      </div>
      <p className="settings-note">{t("permission.hint")}</p>
      {permissions === null ? (
        <p className="settings-note">{reason ?? t("provider.loading")}</p>
      ) : (
        <div className="settings-card">
          {permissions.modes.map((choice) => (
            <button
              key={choice.mode}
              type="button"
              className={
                choice.mode === permissions.mode
                  ? "settings-row permission-choice active"
                  : "settings-row permission-choice"
              }
              aria-pressed={choice.mode === permissions.mode}
              disabled={busy}
              onClick={() => void choose(choice.mode)}
            >
              <div className="row-label">
                <span className="mono">{choice.mode}</span>
                {/* The runtime's own wording, so it cannot drift from what the
                    mode actually does. */}
                <small>{choice.summary}</small>
              </div>
            </button>
          ))}
        </div>
      )}
      {failure && <p className="issue-line">{failure}</p>}
    </>
  );
}

export function Settings({
  group,
  appearance,
  localePreference,
  projectRoot,
  version,
  onSelectGroup,
  onChangeAppearance,
  onChangeLocale,
  onClose
}: {
  group: SettingsGroup;
  appearance: Appearance;
  localePreference: LocalePreference;
  projectRoot: string;
  version: string;
  onSelectGroup: (group: SettingsGroup) => void;
  onChangeAppearance: (patch: Partial<Appearance>) => void;
  onChangeLocale: (preference: LocalePreference) => void;
  onClose: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  // Held by the Agent, which is also what records approvals with it. The
  // local value is just the field being typed into.
  const { operator, reload: reloadOperator } = useOperator(projectRoot, true);
  const [operatorName, setOperatorName] = React.useState("");
  React.useEffect(() => {
    if (operator) setOperatorName(operator.name);
  }, [operator]);
  const apple = isApplePlatform(
    typeof navigator === "undefined" ? "" : navigator.platform || navigator.userAgent
  );

  return (
    <section className="settings">
      <header className="workspace-header" onMouseDown={startWindowDrag}>
        <div className="workspace-title">
          <h1>{t("settings.title")}</h1>
          <p>{t("settings.subtitle")}</p>
        </div>
        <button type="button" className="secondary-button" onClick={onClose}>
          {t("settings.back")}
        </button>
      </header>

      <div className="settings-body">
        <nav className="settings-nav" aria-label={t("settings.title")}>
          {GROUPS.map((candidate) => (
            <button
              key={candidate}
              type="button"
              className={candidate === group ? "nav-item active" : "nav-item"}
              aria-current={candidate === group ? "true" : undefined}
              onClick={() => onSelectGroup(candidate)}
            >
              {t(`settings.group.${candidate}` as MessageKey)}
            </button>
          ))}
        </nav>

        <div className="settings-content">
          <div className="settings-intro">
            <h2>{t(`settings.group.${group}` as MessageKey)}</h2>
            <p>{t(`settings.hint.${group}` as MessageKey)}</p>
          </div>

          {group === "general" && (
            <div className="settings-card">
              {/*
                Recorded on every approval this Workbench makes. Left blank
                deliberately until the user fills it: an approver nobody chose
                would attribute decisions to a placeholder.
              */}
              <Row
                label={t("settings.operator")}
                hint={
                  isConfigured(operator)
                    ? t("settings.operatorHint")
                    : t("settings.operatorMissing")
                }
              >
                <input
                  className="operator-input"
                  value={operatorName}
                  placeholder={t("settings.operatorPlaceholder")}
                  onChange={(event) => setOperatorName(event.target.value)}
                  onBlur={() => {
                    // On blur rather than per keystroke: this is a round trip
                    // to the Agent, and a name is finished being typed once.
                    if (!operatorName.trim() || operatorName === operator?.name) return;
                    void saveOperator(projectRoot, operatorName).then(reloadOperator);
                  }}
                />
              </Row>
              <Row
                label={t("settings.general.restore")}
                hint={t("settings.general.restoreHint")}
              >
                <Toggle
                  checked={appearance.restoreLastProject}
                  label={t("settings.general.restore")}
                  onChange={(restoreLastProject) => onChangeAppearance({ restoreLastProject })}
                />
              </Row>
              <PreviewRow
                label={t("general.index")}
                hint={t("general.indexHint")}
                marker={t("settings.unavailable")}
                value={<Toggle checked label={t("general.index")} onChange={() => undefined} />}
              />
              <PreviewRow
                label={t("general.notify")}
                hint={t("general.notifyHint")}
                marker={t("settings.unavailable")}
                value={<Toggle checked label={t("general.notify")} onChange={() => undefined} />}
              />
              <PreviewRow
                label={t("general.telemetry")}
                hint={t("general.telemetryHint")}
                marker={t("settings.unavailable")}
                value={
                  <Toggle checked={false} label={t("general.telemetry")} onChange={() => undefined} />
                }
              />
              <PreviewRow
                label={t("general.logRetention")}
                hint={t("general.logRetentionHint")}
                marker={t("settings.unavailable")}
                value={<span className="mono">{t("general.logRetentionValue")}</span>}
              />
              <PreviewRow
                label={t("general.shadowWorkspace")}
                hint={t("general.shadowWorkspaceHint")}
                marker={t("settings.unavailable")}
                value={<span className="mono truncate">{t("general.shadowWorkspaceValue")}</span>}
              />
            </div>
          )}

          {group === "appearance" && (
            <div className="settings-card">
              <Row
                label={t("settings.appearance.theme")}
                hint={t("settings.appearance.themeHint")}
              >
                <Segmented<ThemePreference>
                  value={appearance.theme}
                  label={t("settings.appearance.theme")}
                  options={[
                    { id: "dark", label: t("theme.dark") },
                    { id: "light", label: t("theme.light") },
                    { id: "system", label: t("theme.system") }
                  ]}
                  onChange={(theme) => onChangeAppearance({ theme })}
                />
              </Row>
              <Row
                label={t("settings.appearance.density")}
                hint={t("settings.appearance.densityHint")}
              >
                <Segmented<Density>
                  value={appearance.density}
                  label={t("settings.appearance.density")}
                  options={[
                    { id: "compact", label: t("density.compact") },
                    { id: "standard", label: t("density.standard") }
                  ]}
                  onChange={(density) => onChangeAppearance({ density })}
                />
              </Row>
              <Row
                label={t("settings.appearance.accent")}
                hint={t("settings.appearance.accentHint")}
              >
                <div className="swatches" role="radiogroup" aria-label={t("settings.appearance.accent")}>
                  {ACCENTS.map((accent) => {
                    const name = t(`accent.${accent.id}` as MessageKey);
                    return (
                      <button
                        key={accent.id}
                        type="button"
                        role="radio"
                        aria-checked={accent.id === appearance.accent}
                        aria-label={name}
                        title={name}
                        className={accent.id === appearance.accent ? "swatch active" : "swatch"}
                        style={{ background: accentColor(accent.id) }}
                        onClick={() => onChangeAppearance({ accent: accent.id })}
                      />
                    );
                  })}
                </div>
              </Row>
              <PreviewRow
                label={t("appearance.codeSize")}
                hint={t("appearance.codeSizeHint")}
                marker={t("settings.unavailable")}
                value={<span className="mono">11.5 px</span>}
              />
            </div>
          )}

          {group === "language" && (
            <div className="settings-card">
              <Row label={t("settings.language.label")} hint={t("settings.language.hint")}>
                <select
                  className="select"
                  value={localePreference ?? "system"}
                  aria-label={t("settings.language.label")}
                  onChange={(event) => {
                    const next = event.target.value;
                    onChangeLocale(next === "system" ? null : (next as LocalePreference));
                  }}
                >
                  <option value="system">{t("settings.language.system")}</option>
                  {LOCALES.map((locale) => (
                    <option key={locale} value={locale}>
                      {LOCALE_NAMES[locale]}
                    </option>
                  ))}
                </select>
              </Row>
            </div>
          )}

          {group === "provider" && (
            <>
              <p className="settings-note">{t("settings.provider.empty")}</p>
              {/*
                The wizard belongs to the panel that lists providers, so
                saving one can refresh that list. Owned up here it could not:
                the list held its own inventory and nothing could ask it to
                re-read, which is why a saved provider said "saved" and then
                did not appear.
              */}
              <ProviderSettings projectRoot={projectRoot} />
            </>
          )}

          {/*
            Usage shows what accounts have spent. Signing one in belongs to
            the provider wizard, where the account is chosen as an endpoint's
            credential -- offering it here as well made the same account
            reachable from two places and reversed the order: you had to come
            here to sign in before you could finish adding a provider.
          */}
          {group === "usage" && <UsagePanel projectRoot={projectRoot} />}

          {group === "permissions" && (
            <>
              {/*
                Real, and first. What follows is still a mock-up, and a person
                scrolling past a preview banner to reach the one control that
                does something would reasonably conclude none of them work.
              */}
              <PermissionSettings projectRoot={projectRoot} />
              <PreviewBanner />
              <p className="settings-note">{t("settings.permissions.empty")}</p>
              <div className="settings-card">
                <PreviewRow
                  label={t("permissions.sandbox")}
                  hint={t("permissions.sandboxHint")}
                  marker={t("settings.unavailable")}
                  value={<Toggle checked label={t("permissions.sandbox")} onChange={() => undefined} />}
                />
                <PreviewRow
                  label={t("permissions.autoTest")}
                  hint={t("permissions.autoTestHint")}
                  marker={t("settings.unavailable")}
                  value={<Toggle checked label={t("permissions.autoTest")} onChange={() => undefined} />}
                />
                <PreviewRow
                  label={t("permissions.autoCommit")}
                  hint={t("permissions.autoCommitHint")}
                  marker={t("settings.unavailable")}
                  value={
                    <Toggle
                      checked={false}
                      label={t("permissions.autoCommit")}
                      onChange={() => undefined}
                    />
                  }
                />
                <PreviewRow
                  label={t("permissions.runLimit")}
                  hint={t("permissions.runLimitHint")}
                  marker={t("settings.unavailable")}
                  value={<span className="mono">{t("permissions.runLimitValue")}</span>}
                />
              </div>
              <div className="settings-card padded-card">
                <span className="section-title">{t("permissions.toolsAllowed")}</span>
                <div className="chip-wrap">
                  {TOOL_CHIPS.map((chip) => (
                    <span key={chip} className="tool-permission-chip mono">
                      {chip}
                    </span>
                  ))}
                </div>
              </div>
            </>
          )}

          {group === "shortcuts" && (
            <div className="settings-card">
              {SHORTCUTS.map((shortcut) => (
                <div key={shortcut.id} className="settings-row">
                  <div className="row-label">
                    <span>{t(shortcut.labelKey)}</span>
                  </div>
                  <kbd className="keys">{displayShortcut(shortcut, apple)}</kbd>
                </div>
              ))}
            </div>
          )}

          {group === "about" && (
            <div className="settings-card about">
              <div className="about-brand">
                <img
                  src={darkWordmark}
                  alt={t("app.name")}
                  className="wordmark dark"
                  draggable={false}
                />
                <img
                  src={lightWordmark}
                  alt={t("app.name")}
                  className="wordmark light"
                  draggable={false}
                />
              </div>
              <Row label={t("settings.about.version")}>
                <span className="mono">{version}</span>
              </Row>
              <Row label={t("settings.about.runtime")}>
                <span className="mono">{t("settings.about.runtimeValue")}</span>
              </Row>
              {projectRoot && (
                <Row label={t("settings.about.project")}>
                  <span className="mono truncate">{projectRoot}</span>
                </Row>
              )}
            </div>
          )}
        </div>
      </div>

    </section>
  );
}
