import React, { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useI18n } from "../../i18n";
import { Card } from "../primitives";
import { isDesktopRuntime } from "../../agent";
import { type Run, useRunDetail, useRuns, runTone } from "../../runs";

/**
 * Test runs, from the same engine run history the Terminal shows, narrowed to
 * the test operation.
 *
 * The design mocked per-suite pass/fail counts and a frame-rate curve. The core
 * runs the engine headless and captures its process output, so that structure
 * does not exist -- inventing it here would mean parsing engine logs into
 * numbers the runtime never reported.
 */
export function TestWorkspace({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { runs, reason, loading, reload } = useRuns(projectRoot, true, "test");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const selected = selectedId ?? runs[0]?.id ?? null;
  const detail = useRunDetail(projectRoot, selected);

  const runTests = async (): Promise<void> => {
    if (running || !isDesktopRuntime()) return;
    setRunning(true);
    try {
      await invoke("agent_run_engine", { projectPath: projectRoot, operation: "test" });
      reload();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="workspace-body padded">
      <div className="settings-section">
        <span className="section-title">{t("test.lastRun")}</span>
        <button
          type="button"
          className="primary-button small"
          onClick={() => void runTests()}
          disabled={running || !isDesktopRuntime()}
        >
          {running ? t("test.running") : t("test.runNow")}
        </button>
      </div>

      {runs.length === 0 ? (
        <p className="settings-note">
          {loading ? t("runs.loading") : reason ? t("runs.unavailable") : t("test.noRuns")}
        </p>
      ) : (
        <>
          <Card className="suite-list">
            {runs.map((run: Run) => (
              <button
                key={run.id}
                type="button"
                className={run.id === selected ? "suite-row active" : "suite-row"}
                onClick={() => setSelectedId(run.id)}
              >
                <span className={`state-dot ${runTone(run)}`} aria-hidden="true" />
                <span className="suite-name mono">{run.started_at}</span>
                <span className="mono faint suite-time">{run.adapter_version}</span>
                <span className={`mono tone-${runTone(run)} suite-count`}>
                  {run.timed_out
                    ? t("runs.timedOut")
                    : t(`runs.status.${run.status}` as never)}
                </span>
              </button>
            ))}
          </Card>

          {detail && (
            <Card className="failure-card">
              <div className="board-head">
                <span className="mono truncate">{detail.command.join(" ")}</span>
                {detail.exit_code !== null && (
                  <span className="mono faint">
                    {t("runs.exitCode", { code: detail.exit_code })}
                  </span>
                )}
              </div>
              {detail.stderr && <pre className="run-stream error">{detail.stderr}</pre>}
              <pre className="run-stream">{detail.stdout || t("runs.noOutput")}</pre>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
