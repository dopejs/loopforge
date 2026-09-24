import React, { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { useI18n } from "../i18n";
import { type WorkspaceMode, sidebarTitleKey } from "../modes";
import { projectName } from "../projects";
import type { AgentPhase, AgentState } from "../agent";
import { SIDEBAR_ITEMS } from "../fixtures";
import { deleteSession, useSessions } from "../providers";

function ProjectSwitcher({
  projectRoot,
  projectRoots,
  open,
  busy,
  onToggle,
  onClose,
  onSelect,
  onAdd
}: {
  projectRoot: string;
  projectRoots: readonly string[];
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onClose: () => void;
  onSelect: (root: string) => void;
  onAdd: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const menu = useRef<HTMLDivElement>(null);

  // Escape closes the menu wherever focus currently sits.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  return (
    <div className="project-switcher">
      <button
        type="button"
        className={open ? "project-trigger open" : "project-trigger"}
        onClick={onToggle}
        aria-expanded={open}
        aria-haspopup="menu"
        title={projectRoot || t("project.none")}
      >
        <span className="project-dot" aria-hidden="true" />
        <span className="project-identity">
          <span className="project-name">
            {projectRoot ? projectName(projectRoot) : t("project.none")}
          </span>
          <span className="project-path">{projectRoot}</span>
        </span>
        <span className={open ? "chevron open" : "chevron"} aria-hidden="true">
          <Icon name="chevron" size={13} />
        </span>
      </button>

      {open && (
        <>
          <div className="menu-scrim" onClick={onClose} />
          <div className="project-menu" role="menu" ref={menu} aria-label={t("project.switch")}>
            <p className="menu-heading">{t("project.switch")}</p>
            {projectRoots.map((root) => (
              <button
                key={root}
                type="button"
                role="menuitemradio"
                aria-checked={root === projectRoot}
                className={root === projectRoot ? "menu-item selected" : "menu-item"}
                onClick={() => onSelect(root)}
                disabled={busy}
                title={root}
              >
                <span className="menu-check" aria-hidden="true">
                  {root === projectRoot && <Icon name="check" size={11} />}
                </span>
                <span className="project-identity">
                  <span className="project-name">{projectName(root)}</span>
                  <span className="project-path">{root}</span>
                </span>
              </button>
            ))}
            {projectRoots.length > 0 && <div className="menu-divider" />}
            <button
              type="button"
              role="menuitem"
              className="menu-item"
              onClick={onAdd}
              disabled={busy}
            >
              <span className="menu-check" aria-hidden="true">
                <Icon name="plus" size={12} />
              </span>
              <span className="project-name">{busy ? t("project.adding") : t("project.add")}</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function AgentFooter({
  phase,
  state
}: {
  phase: AgentPhase;
  state: AgentState;
}): React.JSX.Element {
  const { t } = useI18n();
  const label = {
    unsupported: t("agent.status.unsupported"),
    "no-project": t("agent.status.noProject"),
    starting: t("agent.status.starting"),
    ready: t("agent.status.ready"),
    offline: t("agent.status.offline")
  }[phase];
  const version = state.runtime?.version?.version;

  return (
    <div className="sidebar-footer">
      <p className={`agent-state ${phase}`}>
        <span className="state-dot" aria-hidden="true" />
        {label}
      </p>
      {state.project && (
        <p className="footer-meta">
          {state.project.stage} · {t("agent.revision", { value: state.project.observed_revision })}
        </p>
      )}
      {version && <p className="footer-meta">{t("agent.runtime")} · {version}</p>}
      {phase === "unsupported" && <p className="footer-meta">{t("agent.unsupportedHint")}</p>}

      {phase === "offline" && state.reason && <p className="footer-error">{state.reason}</p>}
    </div>
  );
}

export function Sidebar(props: {
  mode: WorkspaceMode;
  projectRoot: string;
  projectRoots: readonly string[];
  menuOpen: boolean;
  busy: boolean;
  agentPhase: AgentPhase;
  agentState: AgentState;
  /** The conversation currently on screen, so its row reads as the open one. */
  sessionId?: string;
  /** Bumped when a turn ends; the listing re-reads on it. */
  turns: number;
  onToggleMenu: () => void;
  onCloseMenu: () => void;
  onSelectProject: (root: string) => void;
  onAddProject: () => void;
  onOpenSession: (sessionId: string) => void;
  onNewSession: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [selected, setSelected] = useState(0);
  // Which row is asking, and which is being removed. Both by id rather than by
  // index: the list is re-read after every delete, and an index would confirm
  // one conversation and delete the one that moved into its place.
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  // Chat sessions come from the runtime; the other modes have no Agent
  // capability behind them yet and stay on preview content.
  const live = useSessions(props.projectRoot, props.mode === "chat");
  const { reload } = live;
  const items =
    props.mode === "chat"
      ? live.sessions.map((session) => ({
          id: session.id,
          label: session.title || session.id,
          sub: session.updated_at,
          meta: String(session.message_count),
          tone: undefined
        }))
      : (SIDEBAR_ITEMS[props.mode] ?? []).map((item) => ({ ...item, id: undefined }));

  const remove = async (sessionId: string): Promise<void> => {
    if (removing) return;
    setRemoving(sessionId);
    try {
      await deleteSession(props.projectRoot, sessionId);
      // Deleting the open conversation leaves the transcript showing something
      // that no longer exists, and every later message would continue a
      // conversation the Agent has forgotten.
      if (props.sessionId === sessionId) props.onNewSession();
      reload();
    } catch {
      // Left listed. A row that vanished on a failed delete would say the
      // conversation was gone when it is still on disk.
    } finally {
      setRemoving(null);
      setConfirming(null);
    }
  };

  useEffect(() => setSelected(0), [props.mode]);

  // Two things make the listing stale, and it took both to fix it.
  //
  // A turn creates or lengthens a conversation, so the count has to be re-read
  // when one ends. That was the first half, and on its own it left the list
  // empty for the whole of a session that had not sent anything yet: the app
  // starts, the sidebar asks before the Agent is up, gets nothing, and nothing
  // asks again until the user sends a message -- at which point every stored
  // conversation appears at once, as though sending had created them.
  //
  // So the Agent becoming ready is the other trigger. It is the moment the
  // question first has an answer.
  //
  // Neither fires on the first render: the listing hook fetches on mount
  // already, and asking again immediately would cost two round trips for one
  // answer.
  const seenTurns = useRef(props.turns);
  const seenPhase = useRef(props.agentPhase);
  useEffect(() => {
    if (props.mode !== "chat") return;
    const aTurnEnded = props.turns !== seenTurns.current;
    const becameReady =
      props.agentPhase === "ready" && seenPhase.current !== "ready";
    seenTurns.current = props.turns;
    seenPhase.current = props.agentPhase;
    if (aTurnEnded || becameReady) reload();
  }, [props.agentPhase, props.mode, props.turns, reload]);

  return (
    <aside className="sidebar">
      <ProjectSwitcher
        projectRoot={props.projectRoot}
        projectRoots={props.projectRoots}
        open={props.menuOpen}
        busy={props.busy}
        onToggle={props.onToggleMenu}
        onClose={props.onCloseMenu}
        onSelect={props.onSelectProject}
        onAdd={props.onAddProject}
      />

      <div className="sidebar-section">
        <span className="section-title">{t(sidebarTitleKey(props.mode))}</span>
        {/*
          Without this, opening a stored conversation was a one-way door:
          every later message continued it, and there was no way back to a
          blank one short of restarting the Agent.
        */}
        {props.mode === "chat" ? (
          <button
            type="button"
            className="ghost-button small"
            onClick={props.onNewSession}
          >
            {t("sidebar.newSession")}
          </button>
        ) : (
          <span className="mono faint section-count">{items.length}</span>
        )}
      </div>

      {/*
        Chat lists real sessions; the other modes are still scaffolding, so
        their selection is local and their content comes from fixtures.
      */}
      <div className="sidebar-list">
        {items.map((item, index) => (
          /*
            A row and its delete, side by side. The row is a button and a
            button cannot contain one, so the two are siblings rather than
            nested -- which is also what lets the delete keep its own focus and
            its own label for a screen reader.
          */
          <div className="sidebar-row" key={item.id ?? item.label}>
          <button
            /*
              The conversation, not what it happens to be called. Titles are
              taken from the first message, so three conversations opened with
              "hello" share one -- React then keyed them together and reused
              one row's state for another, and the list read as duplicates of a
              conversation the user could not tell apart from its neighbours.
            */
            type="button"
            className={
              (item.id ? item.id === props.sessionId : index === selected)
                ? "sidebar-item active"
                : "sidebar-item"
            }
            aria-current={
              (item.id ? item.id === props.sessionId : index === selected)
                ? "true"
                : undefined
            }
            /*
              A conversation row reopens that conversation. Selection used to
              be local state and nothing else: the row highlighted and the
              transcript beside it did not change, so stored history was
              visible and unreachable.
            */
            onClick={() => {
              setSelected(index);
              if (item.id) props.onOpenSession(item.id);
            }}
          >
            <span className="item-identity">
              <span className="item-label">{item.label}</span>
              <span className="mono faint item-sub">{item.sub}</span>
            </span>
            {item.meta && (
              <span className={`mono item-meta tone-${item.tone ?? "faint"}`}>{item.meta}</span>
            )}
          </button>
          {/*
            Two steps, and no dialog. Deleting removes the conversation from
            disk and there is no undo, so one stray click must not do it -- but
            a modal per row would make clearing out a dozen test conversations
            a chore, which is what this is for. The row's own buttons become
            the confirmation.
          */}
          {item.id && confirming === item.id ? (
            <span className="sidebar-confirm">
              <button
                type="button"
                className="sidebar-delete danger"
                disabled={removing === item.id}
                onClick={() => void remove(item.id!)}
              >
                {t("sidebar.confirmDelete")}
              </button>
              <button
                type="button"
                className="sidebar-delete"
                onClick={() => setConfirming(null)}
              >
                {t("sidebar.cancelDelete")}
              </button>
            </span>
          ) : (
            item.id && (
              <button
                type="button"
                className="sidebar-delete"
                aria-label={`${t("sidebar.delete")}: ${item.label}`}
                onClick={() => setConfirming(item.id!)}
              >
                ×
              </button>
            )
          )}
          </div>
        ))}
        {items.length === 0 && <p className="sidebar-empty">{t("sidebar.empty")}</p>}
      </div>

      <AgentFooter phase={props.agentPhase} state={props.agentState} />
    </aside>
  );
}
