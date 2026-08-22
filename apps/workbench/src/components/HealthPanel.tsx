import React, { useState } from "react";
import { useI18n } from "../i18n";
import { Card } from "./primitives";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  type Check,
  type Diagnostic,
  type HistoryEvent,
  type ReconcileResult,
  checkTone,
  reconcileProject,
  useHistory,
  useProjectHealth
} from "../health";
import type { MessageKey } from "../i18n/locales/en";

/**
 * Event labels, spelled out rather than interpolated.
 *
 * Building the key from `event_type` casts away the check that makes a missing
 * translation a compile error, and an unmapped type then renders as a blank
 * row -- an audit entry with no name. Unknown types fall back to the raw type,
 * which is honest and visibly not a label.
 */
const EVENT_LABEL: Record<string, MessageKey> = {
  "project.initialized": "event.project.initialized",
  "hypothesis.created": "event.hypothesis.created",
  "stage.transitioned": "event.stage.transitioned",
  "evidence.registered": "event.evidence.registered",
  "run.completed": "event.run.completed",
  "decision.recorded": "event.decision.recorded"
};

/**
 * Whether the recorded state is intact, and the way out when it is not.
 *
 * ADR 0003 makes an interrupted write a normal condition: the event log is
 * canonical and the snapshot derived from it, so a half-finished replacement
 * leaves the two disagreeing. That state blocks every gate, which is why it is
 * called out here rather than left among the diagnostics.
 *
 * Reconcile rewrites derived state and is never automatic. The preview runs
 * first and its result is shown; only then can it be applied.
 */
export function HealthPanel({
  projectRoot,
  onReconciled
}: {
  projectRoot: string;
  onReconciled?: () => void;
}): React.JSX.Element | null {
  const { t } = useI18n();
  const { health, reason, reload } = useProjectHealth(projectRoot, true);
  const [preview, setPreview] = useState<ReconcileResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [showHistory, setShowHistory] = useState(false);

  if (!health || reason || !health.initialized) return null;

  const run = async (apply: boolean): Promise<void> => {
    if (busy || !isDesktopRuntime()) return;
    setBusy(true);
    setFailure(undefined);
    try {
      const result = await reconcileProject(projectRoot, apply);
      if (apply) {
        setPreview(null);
        reload();
        onReconciled?.();
      } else {
        setPreview(result);
      }
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("health.reconcileFailed")));
    } finally {
      setBusy(false);
    }
  };

  const problems = health.diagnostics.length > 0 || !health.valid;

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("health.section")}</span>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setShowHistory(true)}
        >
          {t("health.viewHistory")}
        </button>
      </div>

      <Card className="suite-list">
        {health.needs_reconcile ? (
          <div className="settings-row">
            <div className="row-label">
              <span>{t("health.staleTitle")}</span>
              {/* Says what it blocks, not just that it is wrong: this is the
                  condition behind every refused gate. */}
              <small>{t("health.staleBody")}</small>
            </div>
            <button
              type="button"
              className="primary-button small"
              onClick={() => void run(false)}
              disabled={busy || !isDesktopRuntime()}
            >
              {busy ? t("health.checking") : t("health.preview")}
            </button>
          </div>
        ) : !problems ? (
          <div className="settings-row">
            <div className="row-label">
              <span>{t("health.ok")}</span>
              <small>
                {t("health.okBody", {
                  count: health.event_count ?? 0,
                  revision: health.observed_revision ?? 0
                })}
              </small>
            </div>
            <span className="badge ok">{t("health.valid")}</span>
          </div>
        ) : null}

        {health.diagnostics.map((item: Diagnostic) => (
          <div key={item.code} className="settings-row">
            <div className="row-label">
              <span className="mono">{item.code}</span>
              {/* The core's own wording: it names what to do about it. */}
              <small>{item.message}</small>
            </div>
            <span className={`badge ${item.severity === "error" ? "bad" : ""}`}>
              {t(`health.severity.${item.severity}` as MessageKey)}
            </span>
          </div>
        ))}

        {health.checks.map((item: Check) => (
          <div key={item.code} className="settings-row">
            <div className="row-label">
              <span className="mono">{item.code}</span>
              <small>{item.message}</small>
            </div>
            <span
              className={`badge ${checkTone(item.status) === "ok" ? "ok" : checkTone(item.status) === "bad" ? "bad" : ""}`}
            >
              {t(`health.check.${item.status}` as MessageKey)}
            </span>
          </div>
        ))}
      </Card>

      {preview && (
        <Card className="failure-card">
          <div className="board-head">
            <span>{t("health.previewTitle")}</span>
          </div>
          {preview.actions.length === 0 ? (
            <p className="settings-note">{t("health.nothingToDo")}</p>
          ) : (
            <>
              <ul className="issue-list">
                {preview.actions.map((action) => (
                  <li key={action.action}>
                    {t(`health.action.${action.action}` as MessageKey, {
                      revision: action.target_revision ?? 0
                    })}
                  </li>
                ))}
              </ul>
              <p className="settings-note">{t("health.applyNote")}</p>
              <div className="card-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setPreview(null)}
                >
                  {t("action.cancel")}
                </button>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void run(true)}
                  disabled={busy}
                >
                  {busy ? t("health.applying") : t("health.apply")}
                </button>
              </div>
            </>
          )}
        </Card>
      )}

      {failure && <p className="settings-note tone-bad">{failure}</p>}

      {showHistory && (
        <HistoryDialog projectRoot={projectRoot} onClose={() => setShowHistory(false)} />
      )}
    </>
  );
}

/**
 * The committed event log.
 *
 * The audit trail belongs in the product that produced it: a decision recorded
 * months ago is only defensible if the sequence behind it can be read back.
 */
function HistoryDialog({
  projectRoot,
  onClose
}: {
  projectRoot: string;
  onClose: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const { history, reason } = useHistory(projectRoot, true);

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("health.historyTitle")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <strong>{t("health.historyTitle")}</strong>
          <p className="wizard-note">{t("health.historyIntro")}</p>
        </header>
        <div className="modal-body">
          {reason ? (
            <p className="settings-note">{t("health.historyUnavailable")}</p>
          ) : !history ? (
            <p className="settings-note">{t("health.historyLoading")}</p>
          ) : history.events.length === 0 ? (
            <p className="settings-note">{t("health.historyEmpty")}</p>
          ) : (
            <Card className="suite-list">
              {history.events.map((event: HistoryEvent) => (
                <div key={`${event.revision}-${event.event_type}`} className="settings-row">
                  <div className="row-label">
                    <span className={EVENT_LABEL[event.event_type] ? "" : "mono"}>
                      {EVENT_LABEL[event.event_type]
                        ? t(EVENT_LABEL[event.event_type])
                        : event.event_type}
                    </span>
                    <small className="mono">{event.occurred_at}</small>
                  </div>
                  <span className="mono faint">{event.detail}</span>
                  <span className="mono faint">
                    {t("health.revision", { value: event.revision ?? 0 })}
                  </span>
                </div>
              ))}
            </Card>
          )}
          {history?.truncated && (
            <p className="settings-note">{t("health.historyTruncated")}</p>
          )}
        </div>
        <footer className="modal-foot">
          <span className="faint truncate">{t("health.historyNote")}</span>
          <div className="card-actions">
            <button type="button" className="primary-button" onClick={onClose}>
              {t("action.close")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
