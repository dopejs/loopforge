import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import { buildChatQueryBody, errorMessage } from "./daemon";
import "./styles.css";

type DaemonState = {
  healthy: boolean;
  version?: string;
  error?: string;
  base_url?: string;
  running?: boolean;
  managed?: boolean;
};

type SupervisorState = Omit<DaemonState, "version"> & {
  version?: { version?: string };
  reason?: string;
};

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

type ChatQueryResponse = { reply: string };

function App(): React.JSX.Element {
  const [projectRoot, setProjectRoot] = useState(() => localStorage.getItem("loopforge.projectRoot") ?? "");
  const [baseUrl, setBaseUrl] = useState("");
  const [daemon, setDaemon] = useState<DaemonState>({ healthy: false });
  const [context, setContext] = useState<LoopforgeProjectContext | null>(null);
  const [query, setQuery] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const nativeStatus = useMemo(() => async <T,>(command: string): Promise<T> => invoke<T>(command, { projectPath: projectRoot }), [projectRoot]);
  useEffect(() => {
    let cancelled = false;
    const refresh = async (): Promise<void> => {
      try {
        if (!projectRoot.trim()) {
          setDaemon({ healthy: false, error: "Choose a game project directory to start Kura." });
          return;
        }
        const [status, project] = await Promise.all([
          nativeStatus<SupervisorState>("agent_status"),
          nativeStatus<LoopforgeProjectContext>("project_context").catch(() => null)
        ]);
        if (!status.base_url) {
          setDaemon({
            healthy: status.healthy,
            running: status.running,
            managed: status.managed,
            error: status.reason
          });
          setContext(project);
          return;
        }
        setBaseUrl(status.base_url);
        const [health, version] = await Promise.all([
          invoke<{ ok?: boolean }>("daemon_get", { baseUrl: status.base_url, path: "/healthz" }),
          invoke<{ version?: string }>("daemon_get", { baseUrl: status.base_url, path: "/version" })
        ]);
        if (!cancelled) {
          setDaemon({ ...status, healthy: health.ok === true, version: version.version });
          setContext(project);
        }
      } catch (error) {
        if (!cancelled) setDaemon({ healthy: false, error: error instanceof Error ? error.message : "daemon unavailable" });
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [nativeStatus, projectRoot]);

  const startAgent = async (): Promise<void> => {
    if (!projectRoot.trim() || lifecycleBusy) return;
    setLifecycleBusy(true);
    localStorage.setItem("loopforge.projectRoot", projectRoot.trim());
    try {
      const status = await nativeStatus<DaemonState>("agent_start");
      setDaemon(status);
      if (status.base_url) setBaseUrl(status.base_url);
    } catch (error) {
      setDaemon({ healthy: false, error: errorMessage(error, "failed to start Kura") });
    } finally {
      setLifecycleBusy(false);
    }
  };

  const stopAgent = async (): Promise<void> => {
    if (!projectRoot.trim() || lifecycleBusy) return;
    setLifecycleBusy(true);
    try {
      await nativeStatus("agent_stop");
      setDaemon({ healthy: false });
      setBaseUrl("");
      setContext(null);
    } catch (error) {
      setDaemon({ healthy: false, error: errorMessage(error, "failed to stop Kura") });
    } finally {
      setLifecycleBusy(false);
    }
  };

  const sendQuery = async (): Promise<void> => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setReply("");
    try {
      const result = await invoke<ChatQueryResponse>("daemon_post", {
        baseUrl,
        path: "/v1/chat/query",
        body: buildChatQueryBody(query)
      });
      setReply(result.reply);
    } catch (error) {
      setReply(errorMessage(error, "request failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div><strong>Loopforge Workbench</strong><span className="muted"> local game development agent</span></div>
        <span className="endpoint">Kura {baseUrl || "not started"}</span>
        <div className="lifecycle"><button type="button" onClick={() => void startAgent()} disabled={lifecycleBusy || !projectRoot.trim() || daemon.healthy}>Start</button><button type="button" onClick={() => void stopAgent()} disabled={lifecycleBusy || !projectRoot.trim() || !daemon.managed}>Stop</button></div>
        <span className={daemon.healthy ? "status ready" : "status degraded"}>{daemon.healthy ? `ready ${daemon.version ?? ""}` : "daemon unavailable"}</span>
      </header>
      <section className="workspace">
        <aside className="sidebar">
          <h2>Project</h2>
          <label className="project-root">Root <input value={projectRoot} onChange={(event) => setProjectRoot(event.target.value)} placeholder="/path/to/game" /></label>
          {context ? <><div className="project-id">{context.project_id}</div><div className="stage">{context.stage}</div><p className="muted">Revision {context.observed_revision}</p><h3>Capabilities</h3><ul>{context.capabilities.map((capability) => <li key={capability}>{capability}</li>)}</ul></> : <p className="muted">Start Kura, then sync project context with <code>loopforge agent sync</code>.</p>}
        </aside>
        <section className="content">
          <div className="section-heading"><h1>Agent session</h1><span className="muted">Context is redacted and daemon-owned</span></div>
          <div className="chat-output">{reply || <span className="muted">Ask the agent to inspect the current game project.</span>}</div>
          <div className="composer"><textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="What should Loopforge inspect or plan?" /><button type="button" onClick={() => void sendQuery()} disabled={busy || !daemon.healthy}>{busy ? "Running..." : "Run"}</button></div>
          {daemon.error && <p className="error">{daemon.error}</p>}
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
