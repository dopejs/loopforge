import React, { useState } from "react";
import { useI18n } from "../../i18n";
import { type Run, useRunDetail, useRuns, runTone } from "../../runs";
import { useProjectStatus } from "../../project";

/**
 * Engine run output. Runs are produced by the deterministic core, so this
 * shows what actually ran rather than a synthesized activity log.
 */
export function TerminalWorkspace({
  projectRoot
}: {
  projectRoot: string;
}): React.JSX.Element {
  const { t } = useI18n();
  const { runs, reason, loading } = useRuns(projectRoot, true);
  // An unmanaged folder has no runs and never will; saying "none yet" would
  // suggest waiting for something that cannot happen.
  const { status } = useProjectStatus(projectRoot, true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = selectedId ?? runs[0]?.id ?? null;
  const detail = useRunDetail(projectRoot, selected);

  if (loading && runs.length === 0) {
    return (
      <div className="workspace-body padded">
        <p className="settings-note">{t("runs.loading")}</p>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="workspace-body padded">
        <p className="settings-note">
          {reason
            ? t("runs.unavailable")
            : status?.initialized === true
              ? t("runs.none")
              : t("runs.notAProject")}
        </p>
      </div>
    );
  }

  return (
    <div className="workspace-body run-split">
      <div className="run-list">
        {runs.map((run: Run) => (
          <button
            key={run.id}
            type="button"
            className={run.id === selected ? "run-row active" : "run-row"}
            onClick={() => setSelectedId(run.id)}
          >
            <span className={`state-dot ${runTone(run)}`} aria-hidden="true" />
            <span className="run-identity">
              <span className="mono">{run.operation}</span>
              <span className="mono faint">{run.started_at}</span>
            </span>
            <span className={`mono tone-${runTone(run)}`}>
              {run.timed_out ? t("runs.timedOut") : t(`runs.status.${run.status}` as never)}
            </span>
          </button>
        ))}
      </div>

      <div className="run-output">
        {detail ? (
          <>
            <div className="run-output-head">
              <span className="mono truncate">{detail.command.join(" ")}</span>
              {detail.exit_code !== null && (
                <span className="mono faint">{t("runs.exitCode", { code: detail.exit_code })}</span>
              )}
            </div>
            {/*
              stderr first: a failing run's cause is there, and the stdout
              above it is usually long enough to bury it.
            */}
            {detail.stderr && <pre className="run-stream error">{detail.stderr}</pre>}
            <pre className="run-stream">{detail.stdout || t("runs.noOutput")}</pre>
          </>
        ) : (
          <p className="settings-note">{t("runs.loading")}</p>
        )}
      </div>
    </div>
  );
}
