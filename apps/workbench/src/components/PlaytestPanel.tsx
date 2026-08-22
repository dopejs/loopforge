import React, { useState } from "react";
import { useI18n } from "../i18n";
import { Card } from "./primitives";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  PLAYTEST_LIST_FIELDS,
  PLAYTEST_TEXT_FIELDS,
  type PlaytestReport,
  type PlaytestState,
  draftProtocol,
  emptyReport,
  importReport,
  saveProtocol,
  serializeReport,
  toLines,
  usePlaytest
} from "../playtest";
import type { MessageKey } from "../i18n/locales/en";

const FIELD_KEY: Record<string, MessageKey> = {
  participant_context: "playtest.field.participant_context",
  comprehension_time: "playtest.field.comprehension_time",
  replay_behavior: "playtest.field.replay_behavior",
  raw_observations: "playtest.field.raw_observations",
  confusion_points: "playtest.field.confusion_points",
  failure_points: "playtest.field.failure_points",
  abandonment_points: "playtest.field.abandonment_points",
  strategies: "playtest.field.strategies"
};

/**
 * Writing and recording the protocol a facilitator takes away.
 *
 * The protocol is run somewhere else, by a person, so getting it out of this
 * application matters more than editing it here. The core stores it as
 * free-form Markdown with no schema, which is why the Workbench presents prose
 * and does not pretend to validate it.
 */
function ProtocolDialog({
  projectRoot,
  onClose,
  onSaved
}: {
  projectRoot: string;
  onClose: () => void;
  onSaved: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [content, setContent] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [failure, setFailure] = useState<string>();

  const draft = async (): Promise<void> => {
    if (drafting) return;
    setDrafting(true);
    setFailure(undefined);
    try {
      const result = await draftProtocol(projectRoot);
      setContent(result.content);
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("playtest.draftFailed")));
    } finally {
      setDrafting(false);
    }
  };

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
    } catch {
      // Clipboard access can be denied; the text stays selectable either way.
      setFailure(t("playtest.copyFailed"));
    }
  };

  const save = async (): Promise<void> => {
    if (saving) return;
    setSaving(true);
    setFailure(undefined);
    try {
      await saveProtocol(projectRoot, content);
      onSaved();
      onClose();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("playtest.protocolFailed")));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("playtest.protocolTitle")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("playtest.protocolTitle")}</strong>
          <p className="wizard-note">{t("playtest.protocolIntro")}</p>
        </header>
        <div className="modal-body">
          <div className="draft-row">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void draft()}
              disabled={drafting}
            >
              {drafting ? t("playtest.drafting") : t("playtest.draft")}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void copy()}
              disabled={!content.trim()}
            >
              {copied ? t("playtest.copied") : t("playtest.copy")}
            </button>
          </div>
          <textarea
            className="hypothesis-text"
            rows={16}
            value={content}
            placeholder={t("playtest.protocolPlaceholder")}
            onChange={(event) => {
              setContent(event.target.value);
              setCopied(false);
            }}
          />
          {failure && <p className="settings-note tone-bad">{failure}</p>}
        </div>
        <footer className="modal-foot">
          <span className="faint truncate">{t("playtest.protocolNote")}</span>
          <div className="card-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              {t("action.cancel")}
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => void save()}
              disabled={saving}
            >
              {saving ? t("playtest.savingProtocol") : t("playtest.saveProtocol")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

/**
 * Entering what was observed.
 *
 * Two rules shape this form and neither is cosmetic. Consent starts
 * unanswered and has no default, because "not required" is a claim someone
 * makes about a real person rather than a fallback for an unanswered question.
 * And what was seen is entered separately from what it means, under headings
 * that say so: blending them would destroy the evidentiary value of the record
 * (ADR 0002).
 */
function ReportDialog({
  projectRoot,
  consentValues,
  onClose,
  onSaved
}: {
  projectRoot: string;
  consentValues: readonly string[];
  onClose: () => void;
  onSaved: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [form, setForm] = useState<PlaytestReport>(emptyReport());
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string>();

  const set = (field: keyof PlaytestReport, value: string): void =>
    setForm((current) => ({ ...current, [field]: value }));

  const save = async (): Promise<void> => {
    if (saving) return;
    setSaving(true);
    setFailure(undefined);
    try {
      await importReport(projectRoot, serializeReport(form));
      onSaved();
      onClose();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("playtest.reportFailed")));
    } finally {
      setSaving(false);
    }
  };

  const observationCount = toLines(form.raw_observations).length;

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("playtest.reportTitle")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("playtest.reportTitle")}</strong>
          <p className="wizard-note">{t("playtest.reportIntro")}</p>
        </header>

        <div className="modal-body">
          <div className="settings-section">
            <span className="section-title">{t("playtest.participant")}</span>
          </div>
          <label className="hypothesis-field">
            <span className="hypothesis-field-head">
              <span>{t("playtest.field.participant_context")}</span>
            </span>
            <textarea
              className="hypothesis-text"
              rows={2}
              value={form.participant_context}
              onChange={(event) => set("participant_context", event.target.value)}
            />
          </label>
          {/* A note about a real person, so the privacy expectation is stated
              where the text is entered rather than buried in documentation. */}
          <p className="settings-note">{t("playtest.privacyNote")}</p>

          {/*
            A fieldset rather than a label: a label associates with one form
            control, and wrapping a group of buttons in it is both wrong
            semantically and enough to break their accessible names.
          */}
          <fieldset className="hypothesis-field consent-field">
            <legend className="hypothesis-field-head">{t("playtest.consent")}</legend>
            <div className="consent-row">
              {consentValues.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={form.consent_status === value ? "chip selected" : "chip"}
                  aria-pressed={form.consent_status === value}
                  onClick={() => set("consent_status", value)}
                >
                  {t(`playtest.consent.${value}` as MessageKey)}
                </button>
              ))}
            </div>
          </fieldset>
          <p className="settings-note">{t("playtest.consentNote")}</p>

          <div className="settings-section">
            <span className="section-title">{t("playtest.observed")}</span>
          </div>
          <p className="settings-note">{t("playtest.observedNote")}</p>
          {(["raw_observations", ...PLAYTEST_LIST_FIELDS.slice(1)] as const).map((field) => (
            <label key={field} className="hypothesis-field">
              <span className="hypothesis-field-head">
                <span>{t(FIELD_KEY[field])}</span>
                <span className="faint">{t("playtest.onePerLine")}</span>
              </span>
              <textarea
                className="hypothesis-text"
                rows={3}
                value={form[field]}
                onChange={(event) => set(field, event.target.value)}
              />
            </label>
          ))}
          {(["comprehension_time", "replay_behavior"] as const).map((field) => (
            <label key={field} className="hypothesis-field">
              <span className="hypothesis-field-head">
                <span>{t(FIELD_KEY[field])}</span>
              </span>
              <textarea
                className="hypothesis-text"
                rows={2}
                value={form[field]}
                onChange={(event) => set(field, event.target.value)}
              />
            </label>
          ))}

          <div className="settings-section">
            <span className="section-title">{t("playtest.interpreted")}</span>
          </div>
          {/* Separated from the observations above by its own section and
              stated outright, because the difference is the whole point. */}
          <p className="settings-note">{t("playtest.interpretationNote")}</p>
          <label className="hypothesis-field">
            <span className="hypothesis-field-head">
              <span>{t("playtest.field.interpretation")}</span>
            </span>
            <textarea
              className="hypothesis-text"
              rows={3}
              value={form.interpretation}
              onChange={(event) => set("interpretation", event.target.value)}
            />
          </label>

          {failure && <p className="settings-note tone-bad">{failure}</p>}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">
            {t("playtest.observationCount", { count: observationCount })}
          </span>
          <div className="card-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              {t("action.cancel")}
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => void save()}
              disabled={saving}
            >
              {saving ? t("playtest.importing") : t("playtest.import")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

/**
 * The playtest step: write a protocol, run it elsewhere, bring back a report.
 *
 * Both halves are legal only in PLAYTEST_REQUIRED. Rather than surfacing the
 * core's stage error after the fact, the stage requirement is explained up
 * front and the controls are absent until it holds.
 */
export function PlaytestPanel({
  projectRoot,
  onImported
}: {
  projectRoot: string;
  onImported?: () => void;
}): React.JSX.Element | null {
  const { t } = useI18n();
  const { playtest, reason, reload } = usePlaytest(projectRoot, true);
  const [editing, setEditing] = useState<"protocol" | "report" | null>(null);

  if (!playtest || reason) return null;

  const state: PlaytestState = playtest;
  const hasProtocol = state.protocol !== null;

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("playtest.section")}</span>
        {state.allowed && (
          <button
            type="button"
            className="primary-button small"
            onClick={() => setEditing(hasProtocol ? "report" : "protocol")}
            disabled={!isDesktopRuntime()}
          >
            {hasProtocol ? t("playtest.enterReport") : t("playtest.writeProtocol")}
          </button>
        )}
      </div>

      <Card className="suite-list">
        {!state.allowed ? (
          <p className="settings-note">{t("playtest.stageRequired")}</p>
        ) : hasProtocol ? (
          <div className="settings-row">
            <div className="row-label">
              <span>{t("playtest.protocolReady")}</span>
              <small>{t("playtest.protocolReadyHint")}</small>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setEditing("protocol")}
            >
              {t("playtest.reviseProtocol")}
            </button>
          </div>
        ) : (
          <p className="settings-note">{t("playtest.noProtocol")}</p>
        )}
      </Card>

      {editing === "protocol" && (
        <ProtocolDialog
          projectRoot={projectRoot}
          onClose={() => setEditing(null)}
          onSaved={reload}
        />
      )}
      {editing === "report" && (
        <ReportDialog
          projectRoot={projectRoot}
          consentValues={state.consent_values}
          onClose={() => setEditing(null)}
          onSaved={() => {
            reload();
            onImported?.();
          }}
        />
      )}
    </>
  );
}
