import React from "react";
import { Icon } from "../icons";
import { useI18n } from "../i18n";
import { type WorkspaceMode, isWired, modeDescriptionKey, modeLabelKey } from "../modes";
import type { AgentPhase, AgentState, TranscriptEntry } from "../agent";
import { Composer, Transcript } from "./AgentPanel";
import { CanvasWorkspace } from "./workspaces/Canvas";
import { FlowWorkspace } from "./workspaces/Flow";
import { TestWorkspace } from "./workspaces/Test";
import { DiffWorkspace } from "./workspaces/Diff";
import { TerminalWorkspace } from "./workspaces/Terminal";
import { TasksWorkspace } from "./workspaces/Tasks";
import { AssetsWorkspace } from "./workspaces/Assets";
import { ProfilerWorkspace } from "./workspaces/Profiler";
import { startWindowDrag } from "../window";
import { PreviewBanner } from "./primitives";

function EmptyState({
  icon,
  title,
  body,
  action
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  action?: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">
        {icon}
      </div>
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </div>
  );
}

export function WorkspaceHeader({
  mode,
  running,
  busy,
  disabled,
  onToggleRun
}: {
  mode: WorkspaceMode;
  running: boolean;
  busy: boolean;
  disabled: boolean;
  onToggleRun: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  return (
    <header className="workspace-header" onMouseDown={startWindowDrag}>
      <div className="workspace-title">
        <h1>{t(modeLabelKey(mode))}</h1>
        <p>{t(modeDescriptionKey(mode))}</p>
      </div>
      <button
        type="button"
        className={running ? "danger-button" : "primary-button"}
        onClick={onToggleRun}
        disabled={disabled || busy}
      >
        {running ? t("action.stop") : t("action.run")}
      </button>
    </header>
  );
}

/** Preview workspaces, keyed by mode. `chat` is handled separately below. */
const PREVIEW_WORKSPACES: Record<
  Exclude<WorkspaceMode, "chat">,
  () => React.JSX.Element
> = {
  canvas: CanvasWorkspace,
  flow: FlowWorkspace,
  test: TestWorkspace,
  diff: DiffWorkspace,
  terminal: TerminalWorkspace,
  tasks: TasksWorkspace,
  assets: AssetsWorkspace,
  profiler: ProfilerWorkspace
};

export function Workspace({
  mode,
  projectRoot,
  agentPhase,
  agentState,
  transcript,
  busy,
  composerRef,
  onSend,
  onAddProject,
  addingProject
}: {
  mode: WorkspaceMode;
  projectRoot: string;
  agentPhase: AgentPhase;
  agentState: AgentState;
  transcript: readonly TranscriptEntry[];
  busy: boolean;
  composerRef: React.RefObject<HTMLTextAreaElement | null>;
  onSend: (query: string) => void;
  onAddProject: () => void;
  addingProject: boolean;
}): React.JSX.Element {
  const { t } = useI18n();

  if (!projectRoot) {
    return (
      <div className="workspace-body">
        <EmptyState
          icon={<Icon name="folder" size={26} />}
          title={t("project.emptyTitle")}
          body={t("project.emptyBody")}
          action={
            <button
              type="button"
              className="primary-button"
              onClick={onAddProject}
              disabled={addingProject}
            >
              {addingProject ? t("project.adding") : t("project.add")}
            </button>
          }
        />
      </div>
    );
  }

  if (mode === "chat") {
    return (
      <div className="workspace-body chat">
        <Transcript transcript={transcript} busy={busy} variant="page" />
        <Composer
          disabled={agentPhase !== "ready"}
          busy={busy}
          inputRef={composerRef}
          onSend={onSend}
        />
        {agentPhase === "unsupported" && (
          <p className="workspace-note" role="status">
            {t("agent.unsupportedHint")}
          </p>
        )}
        {agentPhase === "offline" && agentState.reason && (
          <p className="workspace-error" role="status">
            {agentState.reason}
          </p>
        )}
      </div>
    );
  }

  // `isWired` in ../modes.ts is the single record of which workspaces the Agent
  // actually serves; everything else is scaffolding and says so.
  const Preview = PREVIEW_WORKSPACES[mode];
  return (
    <>
      {!isWired(mode) && <PreviewBanner />}
      <Preview />
    </>
  );
}
