/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * What the transcript is left holding when a turn fails.
 *
 * The user sent "我想做一个数独游戏" and got a blank bar. The turn had not hung:
 * it failed in seconds with `chat.query.failed`, carrying the reason -- their
 * OAuth token had expired. The consumer read deltas and session ids and
 * nothing else, so the reason was dropped and the reply was blanked to `""`
 * with `failed` styling. An empty red bubble is indistinguishable from a hang,
 * and the one thing they needed to know was "sign in again".
 */

const invoke = vi.hoisted(() => vi.fn());
const listeners = vi.hoisted(() => ({ current: [] as ((event: unknown) => void)[] }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: (_name: string, handler: (event: unknown) => void) => {
    listeners.current.push(handler);
    return Promise.resolve(() => {});
  }
}));

// `isDesktopRuntime` gates every path here and reads a global the shell
// injects. Set rather than mocked, so the module under test is the real one.
(window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};

const { useAgent } = await import("./agent");

/**
 * Pushes one stream frame at every current listener.
 *
 * The `streamId` is not decoration: the handler drops any frame that does not
 * carry the id of the turn it belongs to, so one window's stream cannot write
 * into another's. A first version of this test omitted it, every frame was
 * discarded, and the tests still went green off the fallback path.
 */
function emit(streamId: string, event: string, data: string): void {
  for (const handler of listeners.current) handler({ payload: { streamId, event, data } });
}

/** Answers `agent_query_stream` by running `frames` against that turn's id. */
function streams(frames: (emitFrame: (event: string, data: string) => void) => void) {
  invoke.mockImplementation((command: string, args?: Record<string, unknown>) => {
    if (command !== "agent_query_stream") return Promise.resolve({ ready: true });
    const streamId = String(args?.streamId ?? "");
    frames((event, data) => emit(streamId, event, data));
    return Promise.resolve();
  });
}

function Harness(): React.JSX.Element {
  const agent = useAgent("/p");
  return (
    <div>
      <button type="button" onClick={() => void agent.send("我想做一个数独游戏")}>
        send
      </button>
      <ul>
        {agent.transcript.map((entry) => (
          <li
            key={entry.id}
            data-failed={entry.failed ? "yes" : "no"}
            data-tool={entry.tool ? `${entry.tool.name}:${entry.tool.status}` : ""}
          >
            {entry.tool
              ? `tool ${entry.tool.name} ${entry.tool.status} ${entry.tool.arguments} ${entry.tool.output ?? ""}`
              : `${entry.author}: ${entry.text}`}
          </li>
        ))}
      </ul>
      <span>{agent.busy ? "busy" : "idle"}</span>
    </div>
  );
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
  listeners.current = [];
});

describe("a turn that fails mid-stream", () => {
  it("leaves the reason in the transcript rather than a blank bubble", async () => {
    // The command resolves only once the stream has reported its failure,
    // which is the real order: the terminal frame arrives, then the SSE
    // request completes.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.failed",
        JSON.stringify({
          status: "failed",
          reply: "",
          errorCode: "http_401",
          error: JSON.stringify({
            error: { message: "OAuth access token has expired. Re-authenticate to continue." }
          })
        })
      );
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    expect(
      await screen.findByText(/Re-authenticate to continue/)
    ).toBeTruthy();
    // Still marked failed: the reason is an explanation, not an answer.
    await waitFor(() =>
      expect(
        screen.getByText(/Re-authenticate/).getAttribute("data-failed")
      ).toBe("yes")
    );
  });

  it("says something when the stream ends silently and explains nothing", async () => {
    // No terminal frame at all. Rarer, and it used to look identical.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    expect(await screen.findByText(/without an answer/)).toBeTruthy();
  });

  it("keeps the answer when one actually arrived", async () => {
    // The failure path must not claim a turn that worked.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame("chat.query.delta", JSON.stringify({ delta: "好的，" }));
      frame("chat.query.delta", JSON.stringify({ delta: "我们开始" }));
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    const reply = await screen.findByText(/好的，我们开始/);
    expect(reply.getAttribute("data-failed")).toBe("no");
  });

  it("stops being busy either way", async () => {
    // Or the composer stays disabled and the turn really is stuck.
    streams((frame) => {
      frame("chat.query.failed", JSON.stringify({ errorCode: "http_502" }));
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    // Busy first, or "idle" is just the state it started in -- which is how a
    // first version of this test passed without the turn ever running.
    await waitFor(() => expect(screen.getByText("busy")).toBeTruthy());
    await waitFor(() => expect(screen.getByText("idle")).toBeTruthy());
    expect(screen.getByText(/http_502/)).toBeTruthy();
  });
});


describe("a turn that runs tools", () => {
  it("shows what the agent is doing while it does it", async () => {
    // The window this exists for: the model asks for a tool, something runs it
    // -- sometimes after asking a person to approve -- and the answer comes
    // rounds later. With only text in the transcript that is a silence, and a
    // person cannot tell work from a hang.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.tool",
        JSON.stringify({
          callId: "toolu_1",
          name: "loopforge__loopforge_init",
          phase: "begin",
          arguments: '{"engine":"unity"}'
        })
      );
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    const card = await screen.findByText(/tool loopforge_init running/);
    // The arguments, not just the name. "The agent ran `init`" has no answer
    // to "initialize what?".
    expect(card.textContent).toContain("unity");
  });

  it("marks the call finished when it finishes", async () => {
    // The `end` frame carries no name, so it has to be matched on the call id.
    // A reader that needed the name would leave every card running forever.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.tool",
        JSON.stringify({
          callId: "toolu_1",
          name: "loopforge__loopforge_init",
          phase: "begin",
          arguments: "{}"
        })
      );
      frame(
        "chat.query.tool",
        JSON.stringify({
          callId: "toolu_1",
          name: "",
          phase: "end",
          output: '{"stage":"DISCOVERY"}',
          success: true
        })
      );
      frame("chat.query.delta", JSON.stringify({ delta: "初始化好了" }));
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    await waitFor(() =>
      expect(screen.getByText(/tool loopforge_init done/)).toBeTruthy()
    );
    expect(screen.getByText(/初始化好了/)).toBeTruthy();
  });

  it("puts the tool before the reply it led to", async () => {
    // The order the work happened in. A card after the answer reads as a
    // footnote about something that was already decided.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.tool",
        JSON.stringify({ callId: "t1", name: "loopforge__loopforge_status", phase: "begin", arguments: "{}" })
      );
      frame("chat.query.delta", JSON.stringify({ delta: "现在是 DISCOVERY" }));
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    await screen.findByText(/现在是 DISCOVERY/);
    const rows = [...document.querySelectorAll("li")].map((row) => row.textContent ?? "");
    const tool = rows.findIndex((row) => row.includes("loopforge_status"));
    const reply = rows.findIndex((row) => row.includes("现在是 DISCOVERY"));
    expect(tool).toBeGreaterThanOrEqual(0);
    expect(tool).toBeLessThan(reply);
  });

  it("keeps the reason a call failed, which is the whole of that card", async () => {
    // What the user saw: two red boxes reading `Failed  loopforge_status` and
    // nothing else. The reason was on the stream all along -- the tool server
    // had died -- and only readable by replaying it by hand.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.tool",
        JSON.stringify({ callId: "t1", name: "loopforge__loopforge_status", phase: "begin", arguments: "{}" })
      );
      frame(
        "chat.query.tool",
        JSON.stringify({
          callId: "t1",
          name: "",
          phase: "end",
          output: "loopforge_status was not run: mcp server became unavailable",
          success: false
        })
      );
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    await waitFor(() => expect(screen.getByText(/loopforge_status failed/)).toBeTruthy());
    const rows = [...document.querySelectorAll("li")].map((row) => row.textContent ?? "");
    expect(rows.join("\n")).toContain("mcp server became unavailable");
  });

  it("marks a call that failed as failed", async () => {
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.tool",
        JSON.stringify({ callId: "t1", name: "loopforge__loopforge_advance", phase: "begin", arguments: "{}" })
      );
      frame(
        "chat.query.tool",
        JSON.stringify({ callId: "t1", name: "", phase: "end", output: "refused", success: false })
      );
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    await waitFor(() =>
      expect(screen.getByText(/tool loopforge_advance failed/)).toBeTruthy()
    );
  });

  it("does not treat a tool card as the turn's answer", async () => {
    // A turn whose only frames are tool calls produced no text, and the
    // failure line has to say so rather than the card standing in for a reply.
    streams((frame) => {
      frame("loopforge.session", JSON.stringify({ sessionId: "ses_1" }));
      frame(
        "chat.query.tool",
        JSON.stringify({ callId: "t1", name: "loopforge__loopforge_status", phase: "begin", arguments: "{}" })
      );
    });

    render(<Harness />);
    screen.getByRole("button", { name: "send" }).click();

    expect(await screen.findByText(/without an answer/)).toBeTruthy();
  });
});
