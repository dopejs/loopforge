import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
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
  const [projectRoot, setProjectRoot] = useState(
    () => localStorage.getItem("loopforge.projectRoot") ?? ""
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
  const agentInvoke = useMemo(
    () => async <T,>(command: string, extra: Record<string, unknown> = {}): Promise<T> =>
      invoke<T>(command, { projectPath: projectRoot, ...extra }),
    [projectRoot]
  );

  useEffect(() => {
    let cancelled = false;
    const refresh = async (): Promise<void> => {
      if (!projectRoot.trim()) {
        setAgent({
          schema_version: "loopforge-agent-status-v1",
          ready: false,
          reason: "Choose a game project directory to start Loopforge Agent."
        });
        return;
      }
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
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentInvoke, projectRoot]);

  const startAgent = async (): Promise<void> => {
    if (!projectRoot.trim() || lifecycleBusy) return;
    setLifecycleBusy(true);
    localStorage.setItem("loopforge.projectRoot", projectRoot.trim());
    try {
      setAgent(await agentInvoke<AgentState>("agent_start"));
    } catch (error) {
      setAgent({
        schema_version: "loopforge-agent-status-v1",
        ready: false,
        reason: errorMessage(error, "failed to start Loopforge Agent")
      });
    } finally {
      setLifecycleBusy(false);
    }
  };

  const stopAgent = async (): Promise<void> => {
    if (!projectRoot.trim() || lifecycleBusy) return;
    setLifecycleBusy(true);
    try {
      await agentInvoke("agent_stop");
      setAgent({ schema_version: "loopforge-agent-status-v1", ready: false });
      setThreadId(undefined);
    } catch (error) {
      setAgent({
        schema_version: "loopforge-agent-status-v1",
        ready: false,
        reason: errorMessage(error, "failed to stop Loopforge Agent")
      });
    } finally {
      setLifecycleBusy(false);
    }
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
  const runtimeVersion = agent.runtime?.version?.version;
  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <strong>Loopforge Workbench</strong>
          <span className="muted"> independent game-development agent</span>
        </div>
        <span className="endpoint">Agent {agent.managed ? "local" : "not started"}</span>
        <div className="lifecycle">
          <button
            type="button"
            onClick={() => void startAgent()}
            disabled={lifecycleBusy || !projectRoot.trim() || agent.ready}
          >
            Start
          </button>
          <button
            type="button"
            onClick={() => void stopAgent()}
            disabled={lifecycleBusy || !projectRoot.trim() || !agent.managed}
          >
            Stop
          </button>
        </div>
        <span className={agent.ready ? "status ready" : "status degraded"}>
          {agent.ready ? `ready ${runtimeVersion ?? ""}` : "agent unavailable"}
        </span>
      </header>
      <section className="workspace">
        <aside className="sidebar">
          <h2>Project</h2>
          <label className="project-root">
            Root
            <input
              value={projectRoot}
              onChange={(event) => setProjectRoot(event.target.value)}
              placeholder="/path/to/game"
            />
          </label>
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
            <p className="muted">Start Loopforge Agent to open this project.</p>
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

createRoot(document.getElementById("root")!).render(<App />);
