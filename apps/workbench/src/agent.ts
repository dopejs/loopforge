import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
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

/**
 * A tool the agent ran, in the transcript where it ran.
 *
 * A turn is no longer one dispatch: the model asks for a tool, something runs
 * it -- sometimes after asking a person -- and the answer comes rounds later.
 * With only text in the transcript that window is a silence, and a person
 * cannot tell work from a hang, or see what the agent actually did to their
 * project. The name and the arguments are what it proposed; `status` is what
 * became of it.
 */
export type ToolRun = {
  callId: string;
  /** As registered, without the server prefix the runtime adds. */
  name: string;
  /** The model's own argument string, passed through rather than parsed. */
  arguments: string;
  status: "running" | "done" | "failed";
  /** What the tool answered, once it has. */
  output?: string;
};

export type TranscriptEntry = {
  id: string;
  author: "user" | "agent";
  text: string;
  /** Set when the entry reports a failed request rather than an agent reply. */
  failed?: boolean;
  /** True while tokens are still arriving for this entry. */
  streaming?: boolean;
  /** Set when the entry reports a tool rather than something anybody said. */
  tool?: ToolRun;
};

/**
 * The runtime prefixes a tool with the server that published it, so
 * `loopforge_status` arrives as `loopforge__loopforge_status`. Shown to a
 * person the prefix is noise: there is one server, and it is named twice.
 */
export function toolLabel(name: string): string {
  const marker = name.indexOf("__");
  return marker === -1 ? name : name.slice(marker + 2);
}

/**
 * A tool frame out of the stream, or `null` for anything else.
 *
 * The `end` frame carries no name -- the runtime's event does not have one --
 * so a reader has to correlate it with the `begin` by `callId`. Returned as it
 * arrives rather than joined here, because joining needs the transcript.
 */
export function streamTool(
  event: string,
  data: string
): { callId: string; name: string; phase: string; arguments: string; output: string; success: boolean } | null {
  if (!event.endsWith("tool")) return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (!parsed || typeof parsed !== "object") return null;
    const frame = parsed as Record<string, unknown>;
    const callId = typeof frame.callId === "string" ? frame.callId : "";
    const phase = typeof frame.phase === "string" ? frame.phase : "";
    if (!callId || (phase !== "begin" && phase !== "end")) return null;
    return {
      callId,
      name: typeof frame.name === "string" ? frame.name : "",
      phase,
      arguments: typeof frame.arguments === "string" ? frame.arguments : "",
      output: typeof frame.output === "string" ? frame.output : "",
      success: frame.success === true
    };
  } catch {
    return null;
  }
}

/** One `agent://stream` payload. */
type StreamEvent = {
  streamId: string;
  event: string;
  data: string;
};

/**
 * One stored conversation, with its messages.
 *
 * Lives here rather than beside `useSessions`: this feeds the transcript, and
 * importing it from the provider module made that module and this one import
 * each other -- `useSessions` needs `isDesktopRuntime`, which is here.
 */
export type SessionDetail = {
  schema_version: "loopforge-session-v1";
  id: string;
  title: string;
  updated_at: string;
  messages: readonly { at: string; author: "user" | "agent"; text: string }[];
};

/** Reads one conversation so it can be reopened. */
export function readSession(
  projectRoot: string,
  sessionId: string
): Promise<SessionDetail> {
  return invoke<SessionDetail>("agent_session", {
    projectPath: projectRoot,
    sessionId
  });
}

/**
 * The conversation a turn belongs to, from the Agent's own opening event.
 *
 * Emitted once, before the first token, because the Agent mints the id when a
 * turn has no thread to continue. Carrying it back is what makes the next
 * message part of the same conversation.
 */
export function sessionOf(event: string, data: string): string | null {
  if (event !== "loopforge.session") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed && typeof parsed === "object" && "sessionId" in parsed) {
      const id = (parsed as { sessionId: unknown }).sessionId;
      return typeof id === "string" && id ? id : null;
    }
  } catch {
    return null;
  }
  return null;
}

/** Extract the incremental text from a Kura chat event payload. */
export function streamDelta(event: string, data: string): string | null {
  if (!event.endsWith("delta")) return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed && typeof parsed === "object" && "delta" in parsed) {
      const delta = (parsed as { delta: unknown }).delta;
      return typeof delta === "string" ? delta : null;
    }
  } catch {
    // A non-JSON delta is still text worth showing rather than dropping.
    return data;
  }
  return null;
}

/**
 * Why a turn ended without an answer, as the stream reported it.
 *
 * Kura's terminal frame carries the reason -- an expired token, a provider
 * that refused, a dispatch that timed out -- and this used to be dropped. The
 * consumer read deltas and session ids and nothing else, so a failed turn left
 * an empty bubble with `failed` styling and not one word about what happened.
 * A person looking at a blank red bar cannot tell a failure from a hang, and
 * the one thing they needed to know here was "sign in again".
 *
 * `null` for anything that is not a terminal failure, including a terminal
 * success: only a frame that says the turn failed is worth interrupting
 * someone with.
 */
export function streamFailure(event: string, data: string): string | null {
  if (!event.endsWith("failed")) return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (!parsed || typeof parsed !== "object") return null;
    const frame = parsed as { error?: unknown; errorCode?: unknown };
    // The provider's own message is usually a JSON envelope of its own. Its
    // `message` is the sentence a person can act on; the envelope is not.
    if (typeof frame.error === "string" && frame.error) {
      try {
        const inner: unknown = JSON.parse(frame.error);
        const message = (inner as { error?: { message?: unknown } })?.error?.message;
        if (typeof message === "string" && message) return message;
      } catch {
        // Not nested. The string itself is the reason.
      }
      return frame.error;
    }
    if (typeof frame.errorCode === "string" && frame.errorCode) return frame.errorCode;
  } catch {
    return null;
  }
  return null;
}

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
  /** The conversation on screen, once one exists. */
  sessionId?: string;
  /** Bumped when a turn ends, so a listing of conversations can re-read. */
  turns: number;
  send: (query: string) => Promise<void>;
  /** Loads a stored conversation and continues it. */
  openSession: (sessionId: string) => Promise<void>;
  /** Leaves the current conversation without ending the Agent. */
  newSession: () => void;
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
  // Mirrored into state so the surface can show which conversation is open;
  // the ref is what the send path reads, because it is written from inside an
  // event listener that closes over its own render.
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  // A turn ending is the only thing that creates or lengthens a conversation,
  // so it is what a listing needs to hear about.
  const [turns, setTurns] = useState(0);
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
    setSessionId(undefined);
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
      const replyId = nextEntryId();
      setTranscript((entries) => [
        ...entries,
        { id: nextEntryId(), author: "user", text: trimmed },
        { id: replyId, author: "agent", text: "", streaming: true }
      ]);

      const streamId = replyId;
      let sawText = false;
      // Why it ended, if the stream said. Kept outside the listener so the
      // terminal frame survives to where the turn is finished.
      let reason: string | null = null;
      // Subscribed before the command is issued: the first delta can arrive
      // before the invoke promise has even been awaited.
      const unlisten = await listen<StreamEvent>("agent://stream", ({ payload }) => {
        if (payload.streamId !== streamId) return;
        // The Agent announces which conversation this turn belongs to before
        // any text arrives, and it was thrown away: the handler only ever
        // looked for deltas. So the next message was sent with no thread, the
        // Agent minted another conversation for it, and every exchange became
        // its own two-message session with nothing before it in view -- the
        // model was answering each question as the first one it had seen.
        const opened = sessionOf(payload.event, payload.data);
        if (opened) {
          threadId.current = opened;
          setSessionId(opened);
          return;
        }
        const failure = streamFailure(payload.event, payload.data);
        if (failure) {
          reason = failure;
          return;
        }
        const tool = streamTool(payload.event, payload.data);
        if (tool) {
          setTranscript((entries) => {
            if (tool.phase === "begin") {
              // Before the reply it belongs to, not after: the model asks for
              // a tool and then answers with what it learned, so the card
              // reads in the order the work happened. The reply entry is
              // already in the list, so this goes in ahead of it.
              const card: TranscriptEntry = {
                id: `tool-${tool.callId}`,
                author: "agent",
                text: "",
                tool: {
                  callId: tool.callId,
                  name: toolLabel(tool.name),
                  arguments: tool.arguments,
                  status: "running"
                }
              };
              const at = entries.findIndex((entry) => entry.id === replyId);
              return at === -1
                ? [...entries, card]
                : [...entries.slice(0, at), card, ...entries.slice(at)];
            }
            // The `end` frame carries no name, so it is matched on the call it
            // finishes rather than on what it finished.
            return entries.map((entry) =>
              entry.tool?.callId === tool.callId
                ? {
                    ...entry,
                    tool: {
                      ...entry.tool,
                      status: tool.success ? "done" : "failed",
                      output: tool.output
                    }
                  }
                : entry
            );
          });
          return;
        }
        const delta = streamDelta(payload.event, payload.data);
        if (delta === null) return;
        sawText = true;
        setTranscript((entries) =>
          entries.map((entry) =>
            entry.id === replyId ? { ...entry, text: entry.text + delta } : entry
          )
        );
      });

      try {
        await agentInvoke<void>("agent_query_stream", {
          query: trimmed,
          threadId: threadId.current,
          streamId
        });
        setTranscript((entries) =>
          entries.map((entry) =>
            entry.id === replyId
              ? {
                  ...entry,
                  streaming: false,
                  // A run that ends without producing text is a failure the
                  // user must see -- which means saying what it was. This used
                  // to blank the text and set `failed`, which rendered an
                  // empty bubble: indistinguishable from a hang, and silent
                  // about a reason the stream had already reported.
                  text: sawText ? entry.text : (reason ?? "The agent ended the turn without an answer"),
                  failed: !sawText
                }
              : entry
          )
        );
      } catch (error) {
        const message = errorMessage(error, "Agent request failed");
        setTranscript((entries) =>
          entries.map((entry) =>
            entry.id === replyId
              ? { ...entry, streaming: false, failed: true, text: message }
              : entry
          )
        );
      } finally {
        unlisten();
        setBusy(false);
        // After the reply, not before: the conversation's title and message
        // count are only final once the turn has been written.
        setTurns((value) => value + 1);
      }
    },
    [agentInvoke, busy]
  );

  /**
   * Reopen a stored conversation.
   *
   * The transcript is replaced rather than appended to, and the thread is
   * adopted, so the next message continues this conversation instead of
   * starting another one beside it.
   */
  const openSession = useCallback(
    async (id: string): Promise<void> => {
      if (busy || !projectRoot || !isDesktopRuntime()) return;
      const detail = await readSession(projectRoot, id);
      threadId.current = detail.id;
      setSessionId(detail.id);
      setTranscript(
        detail.messages.map((message, index) => ({
          id: `${detail.id}-${index}`,
          author: message.author,
          text: message.text
        }))
      );
    },
    [busy, projectRoot]
  );

  /** Start a fresh conversation without stopping the Agent. */
  const newSession = useCallback((): void => {
    if (busy) return;
    threadId.current = undefined;
    setSessionId(undefined);
    setTranscript([]);
  }, [busy]);

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
      setSessionId(undefined);
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
    sessionId,
    turns,
    send,
    openSession,
    newSession,
    start,
    stop
  };
}
