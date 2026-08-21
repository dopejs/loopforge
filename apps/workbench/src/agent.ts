import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ensureAgentReady, errorMessage } from "./daemon";

export type LoopforgeProjectContext = {
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

export type KuraRuntimeState = {
  healthy?: boolean;
  running?: boolean;
  version?: { version?: string };
};

export type AgentState = {
  schema_version: "loopforge-agent-status-v1";
  ready: boolean;
  managed?: boolean;
  project?: LoopforgeProjectContext;
  runtime?: KuraRuntimeState;
  reason?: string;
};

export type AgentQueryResponse = {
  schema_version: "loopforge-agent-response-v1";
  reply: string;
  thread_id?: string;
};

export type TranscriptEntry = {
  id: string;
  author: "user" | "agent";
  text: string;
  /** Set when the entry reports a failed request rather than an agent reply. */
  failed?: boolean;
};

export type AgentPhase = "unsupported" | "no-project" | "starting" | "ready" | "offline";

/**
 * The Agent is reached through Tauri commands, which only exist in the desktop
 * shell. `pnpm dev` serves the same frontend in a plain browser for fast UI
 * work, and there `invoke` is absent — worth saying plainly instead of letting
 * a TypeError surface as the agent's status.
 */
export function isDesktopRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

const STATUS_POLL_INTERVAL_MS = 5000;

function idleState(reason?: string): AgentState {
  return { schema_version: "loopforge-agent-status-v1", ready: false, reason };
}

export function agentPhase(
  projectRoot: string,
  lifecycleBusy: boolean,
  state: AgentState,
  desktop: boolean
): AgentPhase {
  if (!desktop) return "unsupported";
  if (!projectRoot) return "no-project";
  if (lifecycleBusy) return "starting";
  return state.ready ? "ready" : "offline";
}

let transcriptSequence = 0;
function nextEntryId(): string {
  transcriptSequence += 1;
  return `entry-${transcriptSequence}`;
}

export type UseAgent = {
  state: AgentState;
  phase: AgentPhase;
  transcript: readonly TranscriptEntry[];
  busy: boolean;
  lifecycleBusy: boolean;
  send: (query: string) => Promise<void>;
  start: () => Promise<void>;
  stop: () => Promise<void>;
};

/**
 * Owns the Loopforge Agent lifecycle for the selected project: it starts or
 * reconnects the sidecar when the project changes, polls status while it is
 * up, and keeps the chat transcript for the current thread.
 *
 * Every project switch resets the transcript and thread, because a thread only
 * has meaning inside the Agent that produced it.
 */
export function useAgent(projectRoot: string): UseAgent {
  const [state, setState] = useState<AgentState>(() => idleState());
  const [transcript, setTranscript] = useState<readonly TranscriptEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const threadId = useRef<string | undefined>(undefined);
  // Bumped to re-run activation after an explicit stop/start from the header.
  const [activation, setActivation] = useState(0);

  const agentInvoke = useMemo(
    () =>
      async <T,>(command: string, extra: Record<string, unknown> = {}): Promise<T> =>
        invoke<T>(command, { projectPath: projectRoot, ...extra }),
    [projectRoot]
  );

  useEffect(() => {
    threadId.current = undefined;
    setTranscript([]);
  }, [projectRoot]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const refresh = async (): Promise<void> => {
      try {
        const status = await agentInvoke<AgentState>("agent_status");
        if (!cancelled) setState(status);
      } catch (error) {
        if (!cancelled) setState(idleState(errorMessage(error, "Loopforge Agent unavailable")));
      }
    };

    const activate = async (): Promise<void> => {
      if (!isDesktopRuntime()) {
        setState(idleState());
        return;
      }
      if (!projectRoot) {
        setState(idleState());
        return;
      }
      setLifecycleBusy(true);
      setState(idleState());
      try {
        const status = await ensureAgentReady<AgentState>((command) =>
          agentInvoke<AgentState>(command)
        );
        if (!cancelled) setState(status);
      } catch (error) {
        if (!cancelled) {
          setState(idleState(errorMessage(error, "failed to start Loopforge Agent")));
        }
      } finally {
        if (!cancelled) {
          setLifecycleBusy(false);
          timer = window.setInterval(() => void refresh(), STATUS_POLL_INTERVAL_MS);
        }
      }
    };

    void activate();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [activation, agentInvoke, projectRoot]);

  const send = useCallback(
    async (query: string): Promise<void> => {
      const trimmed = query.trim();
      if (!trimmed || busy || !isDesktopRuntime()) return;
      setBusy(true);
      setTranscript((entries) => [
        ...entries,
        { id: nextEntryId(), author: "user", text: trimmed }
      ]);
      try {
        const result = await agentInvoke<AgentQueryResponse>("agent_query", {
          query: trimmed,
          threadId: threadId.current
        });
        threadId.current = result.thread_id;
        setTranscript((entries) => [
          ...entries,
          { id: nextEntryId(), author: "agent", text: result.reply }
        ]);
      } catch (error) {
        setTranscript((entries) => [
          ...entries,
          {
            id: nextEntryId(),
            author: "agent",
            text: errorMessage(error, "Agent request failed"),
            failed: true
          }
        ]);
      } finally {
        setBusy(false);
      }
    },
    [agentInvoke, busy]
  );

  const start = useCallback(async (): Promise<void> => {
    if (!projectRoot || lifecycleBusy || !isDesktopRuntime()) return;
    setActivation((value) => value + 1);
  }, [lifecycleBusy, projectRoot]);

  const stop = useCallback(async (): Promise<void> => {
    if (!projectRoot || lifecycleBusy || !isDesktopRuntime()) return;
    setLifecycleBusy(true);
    try {
      await agentInvoke<AgentState>("agent_stop");
      threadId.current = undefined;
      setState(idleState());
    } catch (error) {
      setState(idleState(errorMessage(error, "failed to stop Loopforge Agent")));
    } finally {
      setLifecycleBusy(false);
    }
  }, [agentInvoke, lifecycleBusy, projectRoot]);

  return {
    state,
    phase: agentPhase(projectRoot, lifecycleBusy, state, isDesktopRuntime()),
    transcript,
    busy,
    lifecycleBusy,
    send,
    start,
    stop
  };
}
