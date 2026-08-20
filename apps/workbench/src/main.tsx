import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import { ensureAgentReady, errorMessage } from "./daemon";
import {
  addProjectRoot,
  loadActiveProject,
  loadProjectRoots,
  projectName,
  saveProjectSelection
} from "./projects";
import "./styles.css";

type LoopforgeProjectContext = {
  schema_version: "game-project-context-v1";
  project_id: string;
  project_root: string;
  observed_revision: number;
  stage: string;
  engine?: string | null;
  capabilities: string[];
  next_actions?: string[];
  redactions?: string[];
};

type KuraRuntimeState = {
  healthy?: boolean;
  running?: boolean;
  version?: { version?: string };
};

type AgentState = {
  schema_version: "loopforge-agent-status-v1";
  ready: boolean;
  managed?: boolean;
  project?: LoopforgeProjectContext;
  runtime?: KuraRuntimeState;
  reason?: string;
};

type AgentQueryResponse = {
  schema_version: "loopforge-agent-response-v1";
  reply: string;
  thread_id?: string;
};

type WorkspaceMode = "explore" | "design" | "build" | "test";

type ModeDefinition = {
  label: string;
  description: string;
  icon: React.ReactNode;
  tools: Array<{ id: string; label: string; icon: React.ReactNode }>;
};

function Icon({ name }: { name: string }): React.JSX.Element {
  const paths: Record<string, React.ReactNode> = {
    explore: <><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></>,
    design: <><path d="M4 19.5 9.5 18l9.7-9.7a2.1 2.1 0 0 0-3-3L6.5 15Z" /><path d="m14.5 6 3 3" /></>,
    build: <><path d="M12 3v18M3 12h18" /><path d="m7 7 10 10M17 7 7 17" /></>,
    test: <><path d="M9 3h6M10 3v5l-5 9a2.5 2.5 0 0 0 2.2 4h9.6a2.5 2.5 0 0 0 2.2-4l-5-9V3" /><path d="M8 15h8" /></>,
    cursor: <path d="m5 3 14 8-6 2-3 6Z" />,
    map: <><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z" /><path d="M9 3v15M15 6v15" /></>,
    note: <><path d="M5 3h14v18H5Z" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    flow: <><circle cx="6" cy="6" r="2" /><circle cx="18" cy="18" r="2" /><path d="M8 6h4a3 3 0 0 1 3 3v6M12 15h3" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
    hammer: <><path d="m14 5 5 5M12 7l5 5M4 20l9-9" /><path d="m10 4 3-2 7 7-2 3Z" /></>,
    terminal: <><path d="m4 6 5 5-5 5M11 18h9" /></>,
    play: <path d="m7 4 13 8-13 8Z" />,
    checklist: <><path d="m4 6 2 2 4-4M4 13l2 2 4-4M13 7h7M13 14h7M4 20h16" /></>,
    bug: <><path d="M8 9h8v8a4 4 0 0 1-8 0ZM10 5h4l2 4H8Z" /><path d="M4 13h4M16 13h4M5 19l3-2M19 19l-3-2" /></>
  };
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

const MODES: Record<WorkspaceMode, ModeDefinition> = {
  explore: {
    label: "Explore",
    description: "Inspect the project and map its current state.",
    icon: <Icon name="explore" />,
    tools: [
      { id: "select", label: "Select", icon: <Icon name="cursor" /> },
      { id: "map", label: "Project map", icon: <Icon name="map" /> }
    ]
  },
  design: {
    label: "Design",
    description: "Shape systems, flows, and player-facing decisions.",
    icon: <Icon name="design" />,
    tools: [
      { id: "notes", label: "Design notes", icon: <Icon name="note" /> },
      { id: "flow", label: "Flow", icon: <Icon name="flow" /> },
      { id: "layers", label: "Systems", icon: <Icon name="layers" /> }
    ]
  },
  build: {
    label: "Build",
    description: "Work with the playable implementation.",
    icon: <Icon name="build" />,
    tools: [
      { id: "build", label: "Build", icon: <Icon name="hammer" /> },
      { id: "console", label: "Console", icon: <Icon name="terminal" /> },
      { id: "run", label: "Run", icon: <Icon name="play" /> }
    ]
  },
  test: {
    label: "Test",
    description: "Run playtests and review evidence.",
    icon: <Icon name="test" />,
    tools: [
      { id: "playtest", label: "Playtest", icon: <Icon name="play" /> },
      { id: "checks", label: "Checks", icon: <Icon name="checklist" /> },
      { id: "issues", label: "Issues", icon: <Icon name="bug" /> }
    ]
  }
};

function App(): React.JSX.Element {
  const [projectRoots, setProjectRoots] = useState<string[]>(() =>
    loadProjectRoots(localStorage)
  );
  const [projectRoot, setProjectRoot] = useState(
    () => loadActiveProject(localStorage, loadProjectRoots(localStorage))
  );
  const [agent, setAgent] = useState<AgentState>({
    schema_version: "loopforge-agent-status-v1",
    ready: false
  });
  const [query, setQuery] = useState("");
  const [reply, setReply] = useState("");
  const [threadId, setThreadId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [selectingProject, setSelectingProject] = useState(false);
  const [mode, setMode] = useState<WorkspaceMode>("explore");
  const [activeTool, setActiveTool] = useState("select");
  const agentInvoke = useMemo(
    () => async <T,>(command: string, extra: Record<string, unknown> = {}): Promise<T> =>
      invoke<T>(command, { projectPath: projectRoot, ...extra }),
    [projectRoot]
  );

  useEffect(() => {
    saveProjectSelection(localStorage, projectRoots, projectRoot);
  }, [projectRoot, projectRoots]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const refresh = async (): Promise<void> => {
      try {
        const status = await agentInvoke<AgentState>("agent_status");
        if (!cancelled) setAgent(status);
      } catch (error) {
        if (!cancelled) {
          setAgent({
            schema_version: "loopforge-agent-status-v1",
            ready: false,
            reason: errorMessage(error, "Loopforge Agent unavailable")
          });
        }
      }
    };
    const activate = async (): Promise<void> => {
      if (!projectRoot) {
        setAgent({
          schema_version: "loopforge-agent-status-v1",
          ready: false,
          reason: "Add a game project folder to begin."
        });
        return;
      }
      setLifecycleBusy(true);
      setAgent({
        schema_version: "loopforge-agent-status-v1",
        ready: false,
        reason: "Starting Loopforge Agent for the selected project."
      });
      try {
        const status = await ensureAgentReady<AgentState>((command) =>
          agentInvoke<AgentState>(command)
        );
        if (!cancelled) setAgent(status);
      } catch (error) {
        if (!cancelled) {
          setAgent({
            schema_version: "loopforge-agent-status-v1",
            ready: false,
            reason: errorMessage(error, "failed to start Loopforge Agent")
          });
        }
      } finally {
        if (!cancelled) {
          setLifecycleBusy(false);
          timer = window.setInterval(() => void refresh(), 5000);
        }
      }
    };
    void activate();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [agentInvoke, projectRoot]);

  const addProject = async (): Promise<void> => {
    if (selectingProject || lifecycleBusy) return;
    setSelectingProject(true);
    try {
      const selected = await invoke<string | null>("select_project_directory");
      if (selected) {
        setProjectRoots((roots) => addProjectRoot(roots, selected));
        setProjectRoot(selected);
        setThreadId(undefined);
        setReply("");
      }
    } catch (error) {
      setAgent({
        schema_version: "loopforge-agent-status-v1",
        ready: false,
        reason: errorMessage(error, "failed to select a project directory")
      });
    } finally {
      setSelectingProject(false);
    }
  };

  const selectProject = (root: string): void => {
    if (lifecycleBusy || root === projectRoot) return;
    setProjectRoot(root);
    setThreadId(undefined);
    setReply("");
  };

  const sendQuery = async (): Promise<void> => {
    if (!query.trim() || busy || !agent.ready) return;
    setBusy(true);
    setReply("");
    try {
      const result = await agentInvoke<AgentQueryResponse>("agent_query", {
        query: query.trim(),
        threadId
      });
      setReply(result.reply);
      setThreadId(result.thread_id);
    } catch (error) {
      setReply(errorMessage(error, "Agent request failed"));
    } finally {
      setBusy(false);
    }
  };

  const context = agent.project;
  const modeDefinition = MODES[mode];
  const activeProjectName = projectRoot ? projectName(projectRoot) : "No project selected";

  const selectMode = (nextMode: WorkspaceMode): void => {
    setMode(nextMode);
    setActiveTool(MODES[nextMode].tools[0].id);
  };

  return (
    <main className="shell">
      <aside className="project-menu">
        <div className="brand-region" data-tauri-drag-region>
          <div className="brand-mark" data-tauri-drag-region>LF</div>
          <strong data-tauri-drag-region>Loopforge</strong>
        </div>
        <div className="project-menu-content">
          <div className="projects-heading">
            <h2>Projects</h2>
            <button
              type="button"
              className="icon-button add-project"
              onClick={() => void addProject()}
              disabled={selectingProject || lifecycleBusy}
              aria-label="Add project"
              title="Add project"
            >
              {selectingProject ? "…" : "+"}
            </button>
          </div>
          <div className="project-list">
            {projectRoots.map((root) => (
              <button
                type="button"
                className={root === projectRoot ? "project active" : "project"}
                key={root}
                onClick={() => selectProject(root)}
                disabled={lifecycleBusy}
                aria-pressed={root === projectRoot}
                title={root}
              >
                <strong>{projectName(root)}</strong>
                <span>{root}</span>
              </button>
            ))}
            {projectRoots.length === 0 && (
              <p className="muted">Add a folder to open it as a Loopforge project.</p>
            )}
          </div>
          <nav className="main-menu" aria-label="Project menu">
            <p className="menu-label">Workspace</p>
            <button type="button" className="menu-item active">Workbench</button>
          </nav>
          {context && (
            <div className="project-summary">
              <span className="stage">{context.stage}</span>
              <span className="muted">Revision {context.observed_revision}</span>
            </div>
          )}
        </div>
      </aside>

      <section className="right-pane">
        <header className="project-header" data-tauri-drag-region>
          <div className="project-title" data-tauri-drag-region>
            <strong data-tauri-drag-region>{activeProjectName}</strong>
            {projectRoot && <span data-tauri-drag-region>{projectRoot}</span>}
          </div>
          <div className="header-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void addProject()}
              disabled={selectingProject || lifecycleBusy}
            >
              {selectingProject ? "Opening…" : "Add project"}
            </button>
          </div>
        </header>

        <section className="workspace">
          <nav className="mode-toolbar" aria-label="Workspace modes and tools">
            <div className="toolbar-group">
              {(Object.entries(MODES) as Array<[WorkspaceMode, ModeDefinition]>).map(
                ([id, definition]) => (
                  <button
                    type="button"
                    key={id}
                    className={id === mode ? "tool-button active" : "tool-button"}
                    onClick={() => selectMode(id)}
                    aria-label={`${definition.label} mode`}
                    aria-pressed={id === mode}
                    title={`${definition.label} mode`}
                  >
                    {definition.icon}
                  </button>
                )
              )}
            </div>
            <div className="toolbar-divider" />
            <div className="toolbar-group">
              {modeDefinition.tools.map((tool) => (
                <button
                  type="button"
                  key={tool.id}
                  className={tool.id === activeTool ? "tool-button active secondary" : "tool-button secondary"}
                  onClick={() => setActiveTool(tool.id)}
                  aria-label={tool.label}
                  aria-pressed={tool.id === activeTool}
                  title={tool.label}
                >
                  {tool.icon}
                </button>
              ))}
            </div>
          </nav>

          <div className="work-surface">
            <div className="surface-heading">
              <span className="eyebrow">{modeDefinition.label} mode</span>
              <h1>{projectRoot ? activeProjectName : "Add a project to begin"}</h1>
              <p>{projectRoot ? modeDefinition.description : "Choose a game project folder to open it in Loopforge."}</p>
            </div>
            {context && (
              <div className="context-card">
                <span>Project context</span>
                <strong>{context.project_id}</strong>
                <small>{context.capabilities.length} capabilities available</small>
              </div>
            )}
          </div>

          <aside className="chat-panel">
            <div className="chat-heading">
              <div>
                <strong>Loopforge Agent</strong>
              </div>
              <span className="muted">Chat</span>
            </div>
            <div className="chat-output">
              {reply || (
                <div className="empty-chat">
                  <strong>How can I help?</strong>
                  <span>Ask the Agent to inspect, plan, or work with this project.</span>
                </div>
              )}
            </div>
            <div className="composer">
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault();
                    void sendQuery();
                  }
                }}
                placeholder="Ask Loopforge…"
              />
              <button
                type="button"
                className="send-button"
                onClick={() => void sendQuery()}
                disabled={busy || !agent.ready}
              >
                {busy ? "Working…" : "Send"}
              </button>
            </div>
            {projectRoot && !lifecycleBusy && agent.reason && (
              <p className="error">{agent.reason}</p>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}

const root = createRoot(document.getElementById("root")!);
root.render(<App />);

if (import.meta.hot) {
  import.meta.hot.dispose(() => root.unmount());
}
