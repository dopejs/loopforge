import React, { useState } from "react";
import { useI18n } from "../../i18n";
import { Card } from "../primitives";
import { errorMessage } from "../../daemon";
import { isDesktopRuntime } from "../../agent";
import { useProjectStatus } from "../../project";
import { isConfigured, loadOperator } from "../../operator";
import {
  STAGES,
  type Requirement,
  advanceStage,
  requirementTone,
  useGate
} from "../../stages";
import type { MessageKey } from "../../i18n/locales/en";

/**
 * Where the project is in its lifecycle, and what stands between it and the
 * next stage.
 *
 * The design drew a generic coding pipeline here -- trigger, plan, edit, test,
 * review -- which belongs to a different product. Loopforge's real flow is the
 * stage machine, and unlike that pipeline it has a live source, so this shows
 * that instead.
 *
 * Legality is never decided here. `next_stages` comes from the Agent, gate
 * requirements are rendered with the core's own remediation text, and
 * advancing is attempted rather than pre-authorised: if the core refuses, its
 * refusal is the message.
 */
export function FlowWorkspace({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { status, reload: reloadStatus } = useProjectStatus(projectRoot, true);
  const current = status?.stage ?? "";
  const [target, setTarget] = useState<string | null>(null);
  const { gate, reason, loading, reload } = useGate(projectRoot, target);
  const [advancing, setAdvancing] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [operator] = useState(() => loadOperator());

  // Default to the first legal successor once the project's stage is known.
  React.useEffect(() => {
    if (target === null && gateTargets(current).length > 0) {
      setTarget(gateTargets(current)[0]);
    }
  }, [current, target]);

  const advance = async (): Promise<void> => {
    if (!target || advancing || !isDesktopRuntime()) return;
    setAdvancing(true);
    setFailure(undefined);
    try {
      await advanceStage(
        projectRoot,
        target,
        isConfigured(operator)
          ? {
              approver_id: operator.id,
              approver_name: operator.name,
              rationale: t("stage.advanceRationale", { stage: target })
            }
          : undefined
      );
      setTarget(null);
      reloadStatus();
      reload();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("stage.advanceFailed")));
    } finally {
      setAdvancing(false);
    }
  };

  if (!status?.initialized) {
    return (
      <div className="workspace-body padded">
        <p className="settings-note">{t("stage.notAProject")}</p>
      </div>
    );
  }

  return (
    <div className="workspace-body padded">
      <div className="flow-grid">
        {STAGES.map((stage) => {
          const reached = stage.id === current;
          const selectable = (gate?.next_stages ?? []).includes(stage.id);
          return (
            <button
              key={stage.id}
              type="button"
              className={`flow-node${reached ? " accent" : ""}${
                stage.id === target ? " selected" : ""
              }`}
              style={{ gridColumn: stage.column, gridRow: stage.row }}
              data-arrow={stage.arrow || undefined}
              disabled={!selectable && !reached}
              onClick={() => selectable && setTarget(stage.id)}
            >
              <div className="node-head">
                <span className={`note-label${reached ? " accent" : ""}`}>
                  {reached ? t("stage.current") : selectable ? t("stage.next") : ""}
                </span>
              </div>
              <strong>{t(`stage.${stage.id}` as MessageKey)}</strong>
              <p className="dim">{t(`stage.${stage.id}.body` as MessageKey)}</p>
            </button>
          );
        })}
      </div>

      <div className="settings-section">
        <span className="section-title">
          {target ? t("stage.gateFor", { stage: t(`stage.${target}` as MessageKey) }) : t("stage.gate")}
        </span>
        {target && (
          <button
            type="button"
            className="primary-button small"
            onClick={() => void advance()}
            disabled={advancing || !isDesktopRuntime()}
          >
            {advancing ? t("stage.advancing") : t("stage.advance")}
          </button>
        )}
      </div>

      <Card className="suite-list">
        {loading && !gate ? (
          <p className="settings-note">{t("stage.loading")}</p>
        ) : reason ? (
          <p className="settings-note">{t("stage.unavailable")}</p>
        ) : !gate || gate.requirements.length === 0 ? (
          <p className="settings-note">{t("stage.terminal")}</p>
        ) : (
          gate.requirements.map((item: Requirement) => (
            <div key={item.code} className="settings-row">
              <div className="row-label">
                <span className="mono">{item.code}</span>
                {/* The core's remediation, verbatim: it names what to do. */}
                <small>{item.message}</small>
              </div>
              <span className={`badge ${requirementTone(item.status) === "ok" ? "ok" : requirementTone(item.status) === "bad" ? "bad" : ""}`}>
                {t(`stage.status.${item.status}` as MessageKey)}
              </span>
            </div>
          ))
        )}
      </Card>

      {!isConfigured(operator) && (
        <p className="settings-note">{t("stage.operatorMissing")}</p>
      )}
      {failure && <p className="settings-note tone-bad">{failure}</p>}
    </div>
  );
}

/** Legal successors are only known from the Agent, so this is a placeholder
 *  until the first gate response arrives -- the spine's next stage. */
function gateTargets(current: string): string[] {
  const index = STAGES.findIndex((stage) => stage.id === current);
  return index >= 0 && index + 1 < STAGES.length ? [STAGES[index + 1].id] : [];
}
