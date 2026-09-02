import React, { useState } from "react";
import { useI18n } from "../i18n";
import { errorMessage } from "../daemon";
import { type Approval, resolveApproval, useApprovals } from "../approvals";

/**
 * The question the Agent is waiting on, where the asking happened.
 *
 * In the transcript rather than in a settings page or a global tray: an
 * approval is part of the turn that raised it, and a person deciding whether
 * the agent may advance a stage needs the conversation that led there. Moved
 * somewhere else it becomes a notification, and a notification is something you
 * clear rather than read.
 *
 * The runtime holds the call open for three minutes. Until this existed the
 * only way to answer was to find the approval id and post to the policy API by
 * hand, so in practice every approval expired.
 */
function Waiting({
  approval,
  projectRoot,
  onAnswered
}: {
  approval: Approval;
  projectRoot: string;
  onAnswered: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();

  const answer = async (approved: boolean): Promise<void> => {
    if (busy) return;
    setBusy(true);
    setFailure(undefined);
    try {
      await resolveApproval(projectRoot, approval.approval_id, approved);
      onAnswered();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("approval.failed")));
      setBusy(false);
    }
  };

  return (
    <article className="approval" aria-live="assertive">
      <header className="approval-head">
        <span className="badge accent">{t("approval.waiting")}</span>
        <span className="mono truncate">{approval.tool || approval.action}</span>
      </header>
      {/*
        What is being approved, not merely that something is. "May the agent run
        `advance`" has no answer without knowing what it would advance to, and
        an approval nobody can read is a rubber stamp with an audit trail.
      */}
      <p className="approval-reason mono">{approval.reason}</p>
      <div className="card-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() => void answer(false)}
        >
          {t("approval.deny")}
        </button>
        <button
          type="button"
          className="primary-button"
          disabled={busy}
          onClick={() => void answer(true)}
        >
          {busy ? t("approval.answering") : t("approval.allow")}
        </button>
      </div>
      {failure && <p className="issue-line">{failure}</p>}
    </article>
  );
}

export function ApprovalPanel({
  projectRoot,
  enabled
}: {
  projectRoot: string;
  /** Only while the Agent could be running; polling a dead one says nothing. */
  enabled: boolean;
}): React.JSX.Element | null {
  const { approvals } = useApprovals(projectRoot, enabled);
  // Answered questions disappear on the next poll. Tracking them here as well
  // keeps a button from sitting enabled for the second it takes to notice.
  const [answered, setAnswered] = useState<readonly string[]>([]);
  const waiting = approvals.filter(
    (approval) => !answered.includes(approval.approval_id)
  );

  if (waiting.length === 0) return null;

  return (
    <div className="approvals">
      {waiting.map((approval) => (
        <Waiting
          key={approval.approval_id}
          approval={approval}
          projectRoot={projectRoot}
          onAnswered={() =>
            setAnswered((seen) => [...seen, approval.approval_id])
          }
        />
      ))}
    </div>
  );
}
