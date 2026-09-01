import { describe, expect, it } from "vitest";
import { sessionOf, streamDelta } from "./agent";

/**
 * Carrying the conversation forward.
 *
 * The Agent announces which conversation a turn belongs to before the first
 * token, because it mints the id when a turn arrives with no thread to
 * continue. The stream handler only ever looked for deltas, so that event was
 * received and dropped: the next message was sent with no thread, the Agent
 * minted another conversation, and every exchange became its own two-message
 * session. On disk that is exactly what it looked like -- five conversations,
 * two messages each -- and the model answered every question as the first one
 * it had ever seen.
 */
describe("sessionOf", () => {
  it("reads the conversation the Agent opened", () => {
    expect(sessionOf("loopforge.session", '{"sessionId":"ses_abc"}')).toBe("ses_abc");
  });

  it("ignores every other event on the same channel", () => {
    // The channel carries the whole stream; only one event names a session.
    expect(sessionOf("chat.delta", '{"delta":"hi"}')).toBeNull();
    expect(sessionOf("chat.completed", "{}")).toBeNull();
    expect(sessionOf("", "")).toBeNull();
  });

  it("does not invent an id from a payload that has none", () => {
    expect(sessionOf("loopforge.session", "{}")).toBeNull();
    expect(sessionOf("loopforge.session", '{"sessionId":""}')).toBeNull();
    expect(sessionOf("loopforge.session", '{"sessionId":42}')).toBeNull();
    expect(sessionOf("loopforge.session", "not json")).toBeNull();
  });

  it("stays distinct from the delta reader, which must not claim it", () => {
    // Both read the same channel. If the delta reader treated the opening
    // event as text, the session id would be printed into the reply.
    expect(streamDelta("loopforge.session", '{"sessionId":"ses_abc"}')).toBeNull();
  });
});
