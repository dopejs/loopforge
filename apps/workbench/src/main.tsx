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
  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <strong>Loopforge Workbench</strong>
          <span className="muted"> independent game-development agent</span>
        </div>
      </header>
      <section className="workspace">
        <aside className="sidebar">
          <div className="projects-heading">
            <h2>Projects</h2>
            <button
              type="button"
              className="add-project"
              onClick={() => void addProject()}
              disabled={selectingProject || lifecycleBusy}
            >
              {selectingProject ? "Opening…" : "Add project"}
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
          {context ? (
            <>
              <div className="project-id">{context.project_id}</div>
              <div className="stage">{context.stage}</div>
              <p className="muted">Revision {context.observed_revision}</p>
              <h3>Capabilities</h3>
              <ul>
                {context.capabilities.map((capability) => (
                  <li key={capability}>{capability}</li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">
              {projectRoot
                ? "The project context will appear when its Agent is ready."
                : "Select a project to load its context automatically."}
            </p>
          )}
        </aside>
        <section className="content">
          <div className="section-heading">
            <h1>Agent session</h1>
            <span className="muted">CLI and Skills run behind the Agent boundary</span>
          </div>
          <div className="chat-output">
            {reply || <span className="muted">Ask Loopforge Agent to inspect the project.</span>}
          </div>
          <div className="composer">
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="What should Loopforge inspect or plan?"
            />
            <button
              type="button"
              onClick={() => void sendQuery()}
              disabled={busy || !agent.ready}
            >
              {busy ? "Running..." : "Run"}
            </button>
          </div>
          {agent.reason && <p className="error">{agent.reason}</p>}
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
