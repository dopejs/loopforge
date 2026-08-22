import React, { useState } from "react";
import { useI18n } from "../i18n";
import { Card } from "./primitives";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import { HYPOTHESIS_FIELDS, type HypothesisFields, useHypothesis } from "../hypothesis";
import { isConfigured, useOperator } from "../operator";
import { type Evidence, useEvidence } from "../evidence";
import {
  DECISION_TARGET,
  type DecisionState,
  recordDecision,
  useDecision
} from "../decision";
import type { MessageKey } from "../i18n/locales/en";

/**
 * Recording keep, kill or refactor.
 *
 * The three outcomes are rendered from one list, in the core's order, with the
 * same control and the same weight. Making `keep` the prominent path would
 * bias the judgement this product exists to make honestly, so nothing here
 * distinguishes them beyond what each one means.
 *
 * Evidence is chosen from what is registered, showing each item's result and
 * trust level: a decision citing evidence the user never saw is ceremony. And
 * a `keep` that does not cite the playtest is refused by the core, so the
 * consequence is stated before the button rather than after the failure.
 */
function DecisionDialog({
  projectRoot,
  state,
  onClose,
  onDecided
}: {
  projectRoot: string;
  state: DecisionState;
  onClose: () => void;
  onDecided: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const { evidence } = useEvidence(projectRoot, true);
  const { hypothesis } = useHypothesis(projectRoot, true);
  const [outcome, setOutcome] = useState("");
  const [cited, setCited] = useState<readonly string[]>([]);
  const [rationale, setRationale] = useState("");
  const [revised, setRevised] = useState<HypothesisFields | null>(null);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string>();
  const { operator } = useOperator(projectRoot, true);

  const toggle = (id: string): void =>
    setCited((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );

  // Seed the revision from the current hypothesis: a refactor is a change to
  // it, not a blank restart.
  const startRefactor = (): void => {
    setOutcome("refactor");
    if (!revised && hypothesis) setRevised({ ...hypothesis.fields });
  };

  const citesPlaytest = state.playtest_evidence_ids.some((id) => cited.includes(id));

  const submit = async (): Promise<void> => {
    if (saving || !outcome) return;
    setSaving(true);
    setFailure(undefined);
    try {
      await recordDecision(projectRoot, {
        decision: outcome,
        evidenceIds: cited,
        rationale,
        revisedFields: outcome === "refactor" ? (revised ?? undefined) : undefined
      });
      onDecided();
      onClose();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("decision.failed")));
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
        aria-label={t("decision.title")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("decision.title")}</strong>
          <p className="wizard-note">{t("decision.intro")}</p>
        </header>

        <div className="modal-body">
          <fieldset className="hypothesis-field consent-field">
            <legend className="hypothesis-field-head">{t("decision.outcome")}</legend>
            <div className="decision-row">
              {state.decisions.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={outcome === value ? "decision-choice selected" : "decision-choice"}
                  aria-pressed={outcome === value}
                  onClick={() => (value === "refactor" ? startRefactor() : setOutcome(value))}
                >
                  <strong>{t(`decision.${value}` as MessageKey)}</strong>
                  <small>{t(`decision.${value}.body` as MessageKey)}</small>
                  <span className="mono faint">
                    {t("decision.leadsTo", { stage: DECISION_TARGET[value] ?? "" })}
                  </span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="settings-section">
            <span className="section-title">{t("decision.evidence")}</span>
          </div>
          <p className="settings-note">{t("decision.evidenceNote")}</p>
          <Card className="suite-list">
            {evidence.length === 0 ? (
              <p className="settings-note">{t("decision.noEvidence")}</p>
            ) : (
              evidence.map((item: Evidence) => (
                <label key={item.id} className="settings-row evidence-choice">
                  <input
                    type="checkbox"
                    checked={cited.includes(item.id)}
                    onChange={() => toggle(item.id)}
                  />
                  <div className="row-label">
                    <span>{t(`evidence.type.${item.type}` as MessageKey)}</span>
                    <small className="mono">{item.path}</small>
                  </div>
                  <span className="mono faint">
                    {t(`evidence.trust.${item.trust_level}` as MessageKey)}
                  </span>
                  <span className="badge">
                    {t(`evidence.result.${item.result}` as MessageKey)}
                  </span>
                </label>
              ))
            )}
          </Card>
          {/*
            Said before the attempt, not after the refusal: the core requires a
            keep to cite the playtest itself, and a keep resting on a build
            alone would claim human support it never had.
          */}
          {outcome === "keep" && !citesPlaytest && (
            <p className="settings-note tone-bad">{t("decision.keepNeedsPlaytest")}</p>
          )}

          {outcome === "refactor" && revised && (
            <>
              <div className="settings-section">
                <span className="section-title">{t("decision.revised")}</span>
              </div>
              <p className="settings-note">{t("decision.revisedNote")}</p>
              {HYPOTHESIS_FIELDS.map((key) => (
                <label key={key} className="hypothesis-field">
                  <span className="hypothesis-field-head">
                    <span>{t(`hypothesis.field.${key}` as MessageKey)}</span>
                  </span>
                  <textarea
                    className="hypothesis-text"
                    rows={2}
                    value={revised[key]}
                    onChange={(event) =>
                      setRevised((current) =>
                        current ? { ...current, [key]: event.target.value } : current
                      )
                    }
                  />
                </label>
              ))}
            </>
          )}

          <div className="settings-section">
            <span className="section-title">{t("decision.rationale")}</span>
          </div>
          <p className="settings-note">
            {isConfigured(operator)
              ? t("decision.rationaleHint", { name: operator?.name ?? "" })
              : t("decision.operatorMissing")}
          </p>
          <textarea
            className="hypothesis-text"
            rows={3}
            value={rationale}
            placeholder={t("decision.rationalePlaceholder")}
            onChange={(event) => setRationale(event.target.value)}
          />

          {failure && <p className="settings-note tone-bad">{failure}</p>}
        </div>

        <footer className="modal-foot">
          <span className="faint truncate">
            {t("decision.citedCount", { count: cited.length })}
          </span>
          <div className="card-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              {t("action.cancel")}
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => void submit()}
              disabled={saving || !outcome}
            >
              {saving ? t("decision.recording") : t("decision.record")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

/**
 * The decision step.
 *
 * Reachable only from PROTOTYPE_DECISION, and the only way out of it: the core
 * refuses a plain advance from that stage, so this is where the project either
 * ends, moves into production, or goes back with a new question.
 */
export function DecisionPanel({
  projectRoot,
  onDecided
}: {
  projectRoot: string;
  onDecided?: () => void;
}): React.JSX.Element | null {
  const { t } = useI18n();
  const { decision, reason, reload } = useDecision(projectRoot, true);
  const [open, setOpen] = useState(false);

  if (!decision || reason) return null;
  // Nothing to show before the project can decide and after it has, except a
  // record of what was decided.
  if (!decision.allowed && !decision.recorded) return null;

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("decision.section")}</span>
        {decision.allowed && (
          <button
            type="button"
            className="primary-button small"
            onClick={() => setOpen(true)}
            disabled={!isDesktopRuntime()}
          >
            {t("decision.open")}
          </button>
        )}
      </div>

      <Card className="suite-list">
        {decision.recorded ? (
          <div className="settings-row">
            <div className="row-label">
              <span>{t(`decision.${decision.recorded.decision}` as MessageKey)}</span>
              <small>{decision.recorded.created_at}</small>
            </div>
            <span className="badge">{t("decision.recorded")}</span>
          </div>
        ) : (
          <p className="settings-note">{t("decision.pending")}</p>
        )}
      </Card>

      {open && (
        <DecisionDialog
          projectRoot={projectRoot}
          state={decision}
          onClose={() => setOpen(false)}
          onDecided={() => {
            reload();
            onDecided?.();
          }}
        />
      )}
    </>
  );
}
