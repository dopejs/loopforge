import React from "react";
import { useI18n } from "../../i18n";
import { Card } from "../primitives";
import { type Claim, claimTone, useProjectStatus } from "../../project";
import type { MessageKey } from "../../i18n/locales/en";

/**
 * Where the project stands: its lifecycle stage and the quality claims derived
 * from registered evidence.
 *
 * The design mocked a four-column task board, which is a generic agent-product
 * shape. Loopforge has no task model; it has a stage machine and orthogonal
 * quality claims, and those are what a user needs to see to decide keep, kill
 * or refactor.
 */
export function TasksWorkspace({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { status, reason, loading } = useProjectStatus(projectRoot, true);

  if (loading && !status) {
    return (
      <div className="workspace-body padded">
        <p className="settings-note">{t("project.loading")}</p>
      </div>
    );
  }

  if (!status || (!status.initialized && !status.reason)) {
    return (
      <div className="workspace-body padded">
        <p className="settings-note">
          {reason ? t("project.unavailable") : t("project.uninitialized")}
        </p>
      </div>
    );
  }

  if (!status.initialized) {
    return (
      <div className="workspace-body padded">
        <p className="settings-note">{status.reason}</p>
      </div>
    );
  }

  return (
    <div className="workspace-body padded">
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">{t("project.stage")}</span>
          <strong className="stat-value">{status.stage}</strong>
          <span className="stat-hint">
            {t("project.revision", { value: status.observed_revision ?? 0 })}
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">{t("project.evidence")}</span>
          <strong className="stat-value">{status.evidence_count ?? 0}</strong>
          <span className="stat-hint">{status.snapshot_status ?? ""}</span>
        </div>
      </div>

      <div className="settings-section">
        <span className="section-title">{t("project.claims")}</span>
      </div>
      <Card className="suite-list">
        {(status.claims ?? []).map((claim: Claim) => (
          <div key={claim.claim} className="settings-row">
            <div className="row-label">
              <span>{t(`claim.${claim.claim}` as MessageKey)}</span>
              <small>{t(`claim.${claim.claim}.hint` as MessageKey)}</small>
            </div>
            <span className="mono faint">
              {t("project.evidenceCount", { count: claim.evidence_count })}
            </span>
            <span className={`badge ${claimTone(claim.status) === "ok" ? "ok" : claimTone(claim.status) === "bad" ? "bad" : ""}`}>
              {t(`claim.status.${claim.status}` as MessageKey)}
            </span>
          </div>
        ))}
      </Card>

      {/*
        Stated rather than implied: a green row means evidence supports that one
        claim, not that the game is good.
      */}
      <p className="settings-note">{t("project.claimsNote")}</p>
    </div>
  );
}
