import { describe, expect, it } from "vitest";
import { streamFailure, streamTool, toolLabel } from "./agent";

/**
 * Why a turn ended without an answer.
 *
 * Kura's terminal frame carries the reason and the consumer dropped it: it
 * read deltas and session ids and nothing else, so a failed turn left an empty
 * bubble with `failed` styling and not one word about what happened. A person
 * looking at a blank red bar cannot tell a failure from a hang -- and the one
 * thing they needed to know was "your sign-in expired".
 */
describe("streamFailure", () => {
  it("reads the provider's own sentence out of the terminal frame", () => {
    // The exact frame that produced the blank bar.
    const data = JSON.stringify({
      dispatchId: "e92f381a",
      status: "failed",
      reply: "",
      errorCode: "http_401",
      error: JSON.stringify({
        type: "error",
        error: {
          type: "authentication_error",
          message: "OAuth access token has expired. Re-authenticate to continue."
        }
      })
    });

    expect(streamFailure("chat.query.failed", data)).toBe(
      "OAuth access token has expired. Re-authenticate to continue."
    );
  });

  it("falls back to the envelope when there is no sentence inside it", () => {
    const data = JSON.stringify({ error: "the dispatch timed out" });
    expect(streamFailure("chat.query.failed", data)).toBe("the dispatch timed out");
  });

  it("falls back to the code when there is no message at all", () => {
    // Worse than a sentence, better than a blank bubble.
    const data = JSON.stringify({ errorCode: "http_502" });
    expect(streamFailure("chat.query.failed", data)).toBe("http_502");
  });

  it("says nothing about a turn that did not fail", () => {
    // Only a frame that says the turn failed is worth interrupting someone
    // with; a completed one is answered by the text that already arrived.
    expect(streamFailure("chat.query.completed", JSON.stringify({ reply: "hi" }))).toBeNull();
    expect(streamFailure("chat.query.delta", JSON.stringify({ delta: "hi" }))).toBeNull();
    expect(streamFailure("loopforge.session", JSON.stringify({ sessionId: "s" }))).toBeNull();
  });

  it("says nothing rather than throwing on a frame it cannot read", () => {
    expect(streamFailure("chat.query.failed", "not json")).toBeNull();
    expect(streamFailure("chat.query.failed", "{}")).toBeNull();
  });
});

/**
 * The tool frames, which used to be dropped on the floor.
 *
 * A turn is no longer one dispatch: the model asks for a tool, something runs
 * it -- sometimes after asking a person -- and the answer comes rounds later.
 * The consumer read deltas and session ids, so that whole window was a silence
 * with nothing said about what the agent was doing to the project.
 */
describe("streamTool", () => {
  it("reads the call the agent is about to make", () => {
    const data = JSON.stringify({
      callId: "toolu_1",
      name: "loopforge__loopforge_init",
      phase: "begin",
      arguments: '{"engine":"unity"}'
    });

    const frame = streamTool("chat.query.tool", data)!;
    expect(frame.callId).toBe("toolu_1");
    expect(frame.phase).toBe("begin");
    expect(frame.arguments).toContain("unity");
  });

  it("reads the call finishing, which carries no name", () => {
    // The runtime's `ToolCallEnd` has no name on it, so a reader has to
    // correlate on the call id. A parser that required a name would drop every
    // completion and leave every card running forever.
    const data = JSON.stringify({
      callId: "toolu_1",
      name: "",
      phase: "end",
      output: '{"stage":"DISCOVERY"}',
      success: true
    });

    const frame = streamTool("chat.query.tool", data)!;
    expect(frame.callId).toBe("toolu_1");
    expect(frame.success).toBe(true);
    expect(frame.output).toContain("DISCOVERY");
  });

  it("says nothing about text frames", () => {
    expect(streamTool("chat.query.delta", JSON.stringify({ delta: "hi" }))).toBeNull();
    expect(streamTool("chat.query.completed", "{}")).toBeNull();
  });

  it("refuses a frame it cannot place", () => {
    // A frame with no call has nothing to open or close.
    expect(streamTool("chat.query.tool", JSON.stringify({ phase: "begin" }))).toBeNull();
    expect(streamTool("chat.query.tool", JSON.stringify({ callId: "c" }))).toBeNull();
    expect(streamTool("chat.query.tool", "not json")).toBeNull();
  });
});

describe("toolLabel", () => {
  it("drops the server prefix the runtime adds", () => {
    // There is one server and it is named twice; the prefix is noise.
    expect(toolLabel("loopforge__loopforge_init")).toBe("loopforge_init");
  });

  it("leaves a name that carries no prefix alone", () => {
    expect(toolLabel("loopforge_init")).toBe("loopforge_init");
  });
});
