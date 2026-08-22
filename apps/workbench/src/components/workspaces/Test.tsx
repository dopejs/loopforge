import React, { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useI18n } from "../../i18n";
import { Card } from "../primitives";
import { isDesktopRuntime } from "../../agent";
import { type Run, type RunStatus, useRunDetail, useRuns, runTone } from "../../runs";
import type { MessageKey } from "../../i18n/locales/en";

type Operation = "build" | "test";

/**
 * Message keys per operation, spelled out rather than interpolated.
 *
 * `en.ts` is the typed source of truth, so a literal key that loses its
 * translation is a compile error. Building the key from a variable would cast
 * that guarantee away exactly where a new operation is most likely to be added
 * without its strings.
 */
const OPERATION_LABEL: Record<Operation, MessageKey> = {
  build: "test.buildLabel",
  test: "test.testLabel"
};

const OPERATION_ACTION: Record<Operation, MessageKey> = {
  build: "test.runBuild",
  test: "test.runTest"
};

/** Exhaustive by type, so a new RunStatus cannot ship without its string. */
const STATUS_LABEL: Record<RunStatus, MessageKey> = {
  completed: "runs.status.completed",
  failed: "runs.status.failed",
  interrupted: "runs.status.interrupted",
  unknown: "runs.status.unknown"
};

function statusText(run: Run, t: (key: MessageKey) => string): string {
  return run.timed_out ? t("runs.timedOut") : t(STATUS_LABEL[run.status]);
}

/** Run records carry an unconstrained operation; unknown ones stay readable. */
function operationLabel(operation: string): MessageKey | null {
  return operation === "build" || operation === "test"
    ? OPERATION_LABEL[operation]
    : null;
}

/**
 * Engine runs, and the two controls that produce them.
 *
 * Build and test live on one surface deliberately: TECHNICALLY_VALIDATED is
 * satisfied only when a build and a test have both passed, so splitting the
 * triggers across workspaces would hide the one fact a user needs to act on.
 * Running only tests leaves the claim at `unknown` forever, which reads as a
 * broken product rather than an incomplete one.
 *
 * The design mocked per-suite pass/fail counts and a frame-rate curve. The core
 * runs the engine headless and captures its process output, so that structure
 * does not exist -- inventing it here would mean parsing engine logs into
 * numbers the runtime never reported.
 */
export function TestWorkspace({ projectRoot }: { projectRoot: string }): React.JSX.Element {
  const { t } = useI18n();
  const { runs, reason, loading, reload } = useRuns(projectRoot, true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [running, setRunning] = useState<Operation | null>(null);
  const selected = selectedId ?? runs[0]?.id ?? null;
  const detail = useRunDetail(projectRoot, selected);

  // Runs arrive newest first, so the first match is the current one.
  const latest = (operation: Operation): Run | undefined =>
    runs.find((run) => run.operation === operation);

  const run = async (operation: Operation): Promise<void> => {
    if (running || !isDesktopRuntime()) return;
    setRunning(operation);
    try {
      await invoke("agent_run_engine", { projectPath: projectRoot, operation });
      reload();
    } finally {
      setRunning(null);
    }
  };

  const operationRow = (operation: Operation): React.JSX.Element => {
    const current = latest(operation);
    const busy = running === operation;
    return (
      <div className="settings-row">
        <div className="row-label">
          <span>{t(OPERATION_LABEL[operation])}</span>
          <small>{current ? current.started_at : t("test.notRun")}</small>
        </div>
        <span className={`badge ${current ? runTone(current) : ""}`}>
          {current ? statusText(current, t) : t("test.notRun")}
        </span>
        <button
          type="button"
          className="primary-button small"
          onClick={() => void run(operation)}
          disabled={running !== null || !isDesktopRuntime()}
        >
          {busy ? t("test.running") : t(OPERATION_ACTION[operation])}
        </button>
      </div>
    );
  };

  return (
    <div className="workspace-body padded">
      <div className="settings-section">
        <span className="section-title">{t("test.technical")}</span>
      </div>
      <Card className="suite-list">
        {operationRow("build")}
        {operationRow("test")}
      </Card>
      {/*
        Stated rather than implied: users who run only tests would otherwise
        have no way to learn why the claim never moves.
      */}
      <p className="settings-note">{t("test.bothRequired")}</p>

      <div className="settings-section">
        <span className="section-title">{t("test.lastRun")}</span>
      </div>
      {runs.length === 0 ? (
        <p className="settings-note">
          {loading ? t("runs.loading") : reason ? t("runs.unavailable") : t("runs.none")}
        </p>
      ) : (
        <>
          <Card className="suite-list">
            {runs.map((item: Run) => (
              <button
                key={item.id}
                type="button"
                className={item.id === selected ? "suite-row active" : "suite-row"}
                onClick={() => setSelectedId(item.id)}
              >
                <span className={`state-dot ${runTone(item)}`} aria-hidden="true" />
                <span className="suite-name mono">{item.started_at}</span>
                <span className="mono faint suite-time">
                  {operationLabel(item.operation)
                    ? t(operationLabel(item.operation) as MessageKey)
                    : item.operation}
                </span>
                <span className={`mono tone-${runTone(item)} suite-count`}>
                  {statusText(item, t)}
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
