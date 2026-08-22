import React, { useState } from "react";
import { useI18n } from "../i18n";
import { errorMessage } from "../daemon";
import { Card } from "./primitives";
import {
  HYPOTHESIS_FIELDS,
  type Hypothesis,
  type HypothesisField,
  type HypothesisFields,
  createHypothesis,
  draftHypothesis,
  emptyFields,
  useHypothesis
} from "../hypothesis";
import { isConfigured, useOperator } from "../operator";
import type { MessageKey } from "../i18n/locales/en";

/**
 * Review and record a discovery hypothesis.
 *
 * The user is not handed eleven empty boxes. The agent drafts from a one-line
 * brief and this is the review surface over that draft: every field stays
 * individually editable, and nothing is recorded until the user submits what
 * they have read.
 *
 * Missing fields are marked but submission is not blocked. The core decides
 * whether a hypothesis is complete; a form that disabled its own button would
 * be a second implementation of that rule, and the two would eventually
 * disagree.
 */
export function HypothesisEditor({
  projectRoot,
  initial,
  onClose,
  onSaved
}: {
  projectRoot: string;
  initial: Hypothesis | null;
  onClose: () => void;
  onSaved: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [fields, setFields] = useState<HypothesisFields>(initial?.fields ?? emptyFields());
  const [brief, setBrief] = useState("");
  const [rationale, setRationale] = useState("");
  // Read from the Agent, which is also what records it: the dialog only needs
  // to know whether a name exists so it can say so.
  const { operator } = useOperator(projectRoot, true);
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string>();

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const missing = HYPOTHESIS_FIELDS.filter((key) => !fields[key].trim());

  const draft = async (): Promise<void> => {
    if (drafting || !brief.trim()) return;
    setDrafting(true);
    setFailure(undefined);
    try {
      const result = await draftHypothesis(projectRoot, brief);
      // Merged rather than replaced: a second draft must not silently discard
      // edits the user already made to a field the model left blank.
      setFields((current) => {
        const merged = { ...current };
        for (const key of HYPOTHESIS_FIELDS) {
          if (result.fields[key]?.trim()) merged[key] = result.fields[key];
        }
        return merged;
      });
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("hypothesis.draftFailed")));
    } finally {
      setDrafting(false);
    }
  };

  const save = async (): Promise<void> => {
    if (saving) return;
    setSaving(true);
    setFailure(undefined);
    try {
      await createHypothesis(projectRoot, fields, rationale);
      onSaved();
      onClose();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("hypothesis.saveFailed")));
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
        aria-label={t("hypothesis.title")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("hypothesis.title")}</strong>
          <p className="wizard-note">{t("hypothesis.intro")}</p>
        </header>

        <div className="modal-body">
          <div className="settings-row">
            <div className="row-label">
              <span>{t("hypothesis.brief")}</span>
              <small>{t("hypothesis.briefHint")}</small>
            </div>
          </div>
          <div className="draft-row">
            <input
              className="hypothesis-brief"
              value={brief}
              placeholder={t("hypothesis.briefPlaceholder")}
              onChange={(event) => setBrief(event.target.value)}
            />
            <button
              type="button"
              className="secondary-button"
              onClick={() => void draft()}
              disabled={drafting || !brief.trim()}
            >
              {drafting ? t("hypothesis.drafting") : t("hypothesis.draft")}
            </button>
          </div>

          <div className="hypothesis-fields">
            {HYPOTHESIS_FIELDS.map((key: HypothesisField) => (
              <label key={key} className="hypothesis-field">
                <span className="hypothesis-field-head">
                  <span>{t(`hypothesis.field.${key}` as MessageKey)}</span>
                  {!fields[key].trim() && (
                    <span className="badge">{t("hypothesis.missing")}</span>
                  )}
                </span>
                <textarea
                  className="hypothesis-text"
                  rows={3}
                  value={fields[key]}
                  onChange={(event) =>
                    setFields((current) => ({ ...current, [key]: event.target.value }))
                  }
                />
              </label>
            ))}
          </div>
          {/*
            The gate for leaving discovery requires an approval on the record
            itself, so this is not optional decoration. It is checksummed under
            the operator's name, which is why it is written here rather than
            drafted by the agent.
          */}
          <div className="settings-row">
            <div className="row-label">
              <span>{t("hypothesis.rationale")}</span>
              <small>
                {isConfigured(operator)
                  ? t("hypothesis.rationaleHint", { name: operator?.name ?? "" })
                  : t("hypothesis.operatorMissing")}
              </small>
            </div>
          </div>
          <textarea
            className="hypothesis-text"
            rows={2}
            value={rationale}
            placeholder={t("hypothesis.rationalePlaceholder")}
            onChange={(event) => setRationale(event.target.value)}
          />

          {failure && <p className="settings-note tone-bad">{failure}</p>}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">
            {missing.length > 0
              ? t("hypothesis.missingCount", { count: missing.length })
              : t("hypothesis.complete")}
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
              {saving ? t("hypothesis.saving") : t("hypothesis.save")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

/**
 * The hypothesis as it stands, and the way in to change it.
 *
 * Shown at every stage, not only discovery: a decision recorded months later
 * cites this record, so it has to remain readable once the project has moved
 * on. The core only accepts a new revision during discovery, so later stages
 * say why rather than offering a control that would be refused.
 */
export function HypothesisSection({
  projectRoot,
  stage
}: {
  projectRoot: string;
  stage: string;
}): React.JSX.Element {
  const { t } = useI18n();
  const { hypothesis, reason, loading, reload } = useHypothesis(projectRoot, true);
  const [editing, setEditing] = useState(false);
  const editable = stage === "DISCOVERY";

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("hypothesis.section")}</span>
        {editable && (
          <button
            type="button"
            className="primary-button small"
            onClick={() => setEditing(true)}
          >
            {hypothesis?.present ? t("hypothesis.revise") : t("hypothesis.start")}
          </button>
        )}
      </div>

      <Card className="suite-list">
        {loading && !hypothesis ? (
          <p className="settings-note">{t("hypothesis.loading")}</p>
        ) : reason ? (
          <p className="settings-note">{t("hypothesis.unavailable")}</p>
        ) : hypothesis?.present ? (
          <>
            <div className="settings-row">
              <div className="row-label">
                <span>{t("hypothesis.claim")}</span>
                <small>{hypothesis.fields.hypothesis}</small>
              </div>
              <span className="mono faint">
                {t("hypothesis.revision", { value: hypothesis.revision ?? 1 })}
              </span>
            </div>
            {/* Keep and kill signals are what a later decision is judged
                against, so they stay visible rather than living in a dialog. */}
            <div className="settings-row">
              <div className="row-label">
                <span>{t("hypothesis.field.keep_signals")}</span>
                <small>{hypothesis.fields.keep_signals}</small>
              </div>
            </div>
            <div className="settings-row">
              <div className="row-label">
                <span>{t("hypothesis.field.kill_signals")}</span>
                <small>{hypothesis.fields.kill_signals}</small>
              </div>
            </div>
          </>
        ) : (
          <p className="settings-note">{t("hypothesis.none")}</p>
        )}
      </Card>

      {!editable && <p className="settings-note">{t("hypothesis.discoveryOnly")}</p>}

      {editing && (
        <HypothesisEditor
          projectRoot={projectRoot}
          initial={hypothesis}
          onClose={() => setEditing(false)}
          onSaved={reload}
        />
      )}
    </>
  );
}
