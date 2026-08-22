import { describe, expect, it } from "vitest";
import { streamDelta } from "./agent";

describe("streamDelta", () => {
  it("extracts the incremental text from a delta event", () => {
    expect(streamDelta("chat.query.delta", JSON.stringify({ delta: "hi" }))).toBe("hi");
  });

  it("ignores non-delta events", () => {
    // Started and completed events carry metadata, not text; treating them as
    // text would inject JSON into the reply.
    expect(streamDelta("chat.query.started", JSON.stringify({ delta: "x" }))).toBeNull();
    expect(streamDelta("chat.query.completed", JSON.stringify({ reply: "x" }))).toBeNull();
  });

  it("ignores a delta event whose payload carries no text", () => {
    expect(streamDelta("chat.query.delta", JSON.stringify({ reply: "full" }))).toBeNull();
    expect(streamDelta("chat.query.delta", JSON.stringify({ delta: 42 }))).toBeNull();
  });

  it("falls back to the raw payload when it is not JSON", () => {
    // A provider that streams plain text should still render rather than
    // silently dropping every chunk.
    expect(streamDelta("chat.query.delta", "plain text")).toBe("plain text");
  });

  it("preserves whitespace, which carries word boundaries", () => {
    expect(streamDelta("chat.query.delta", JSON.stringify({ delta: " world" }))).toBe(" world");
  });
});
