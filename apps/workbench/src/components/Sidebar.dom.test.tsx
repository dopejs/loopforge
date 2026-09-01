/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The conversation list.
 *
 * The Agent persists every conversation to disk and serves them from
 * `/v1/sessions`; the sidebar still read `0`. Two separate reasons, and the
 * user saw one symptom: the listing was fetched once when the mode was opened
 * and never again, so a read that beat the Agent to being ready stayed empty
 * for the life of the window; and a row, once listed, only moved a local
 * highlight -- the stored history was visible and unreachable.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", async () => {
  const actual = await vi.importActual<typeof import("../agent")>("../agent");
  return { ...actual, isDesktopRuntime: () => true };
});

vi.mock("../i18n", async () => {
  const { en } = await import("../i18n/locales/en");
  return {
    useI18n: () => ({
      t: (key: string) => {
        const template = (en as Record<string, string>)[key];
        if (template === undefined) throw new Error(`missing message key: ${key}`);
        return template;
      }
    })
  };
});

const { Sidebar } = await import("./Sidebar");

/** How many times the Agent has been asked for the listing. */
let listed = 0;
let sessions: unknown[] = [];

function mockAgent(): void {
  listed = 0;
  invoke.mockImplementation((command: string) => {
    if (command === "agent_sessions") {
      listed += 1;
      return Promise.resolve({ schema_version: "loopforge-session-v1", sessions });
    }
    return Promise.resolve({});
  });
}

function draw(overrides: Record<string, unknown> = {}) {
  return render(
    <Sidebar
      mode="chat"
      projectRoot="/p"
      projectRoots={["/p"]}
      menuOpen={false}
      busy={false}
      agentPhase="ready"
      agentState={{ ready: true } as never}
      turns={0}
      onToggleMenu={() => {}}
      onCloseMenu={() => {}}
      onSelectProject={() => {}}
      onAddProject={() => {}}
      onOpenSession={() => {}}
      onNewSession={() => {}}
      {...overrides}
    />
  );
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
  sessions = [];
});

describe("Sidebar conversations", () => {
  it("lists the conversations the Agent has stored", async () => {
    sessions = [
      { id: "ses_a", title: "你好", updated_at: "2026-09-01T14:27:03Z", message_count: 2 }
    ];
    mockAgent();
    draw();

    expect(await screen.findByText("你好")).toBeTruthy();
  });

  it("asks again once a turn has ended", async () => {
    // A turn is the only thing that creates or lengthens a conversation. The
    // listing was fetched on mount and never again, so the count stayed at
    // whatever it read before the first message was ever sent.
    mockAgent();
    const view = draw({ turns: 0 });
    await waitFor(() => expect(listed).toBe(1));

    sessions = [
      { id: "ses_a", title: "你好", updated_at: "2026-09-01T14:27:03Z", message_count: 2 }
    ];
    view.rerender(
      <Sidebar
        mode="chat"
        projectRoot="/p"
        projectRoots={["/p"]}
        menuOpen={false}
        busy={false}
        agentPhase="ready"
        agentState={{ ready: true } as never}
        turns={1}
        onToggleMenu={() => {}}
        onCloseMenu={() => {}}
        onSelectProject={() => {}}
        onAddProject={() => {}}
        onOpenSession={() => {}}
        onNewSession={() => {}}
      />
    );

    await waitFor(() => expect(listed).toBe(2));
    expect(await screen.findByText("你好")).toBeTruthy();
  });

  it("reopens the conversation a row names", async () => {
    // Clicking used to set a local index and nothing else: the row lit up and
    // the transcript beside it did not change.
    sessions = [
      { id: "ses_a", title: "你好", updated_at: "2026-09-01T14:27:03Z", message_count: 2 }
    ];
    mockAgent();
    const opened = vi.fn();
    draw({ onOpenSession: opened });

    fireEvent.click(await screen.findByText("你好"));

    expect(opened).toHaveBeenCalledWith("ses_a");
  });

  it("marks the open conversation rather than the last one clicked", async () => {
    sessions = [
      { id: "ses_a", title: "first", updated_at: "2026-09-01T14:00:00Z", message_count: 2 },
      { id: "ses_b", title: "second", updated_at: "2026-09-01T13:00:00Z", message_count: 2 }
    ];
    mockAgent();
    draw({ sessionId: "ses_b" });

    const current = await screen.findByText("second");
    expect(current.closest("button")?.getAttribute("aria-current")).toBe("true");
    expect(
      screen.getByText("first").closest("button")?.getAttribute("aria-current")
    ).toBeNull();
  });

  it("offers a way back to a blank conversation", async () => {
    // Opening a stored one was otherwise a one-way door: every later message
    // continued it, with no way back short of restarting the Agent.
    mockAgent();
    const fresh = vi.fn();
    draw({ onNewSession: fresh });

    fireEvent.click(await screen.findByRole("button", { name: "New conversation" }));

    expect(fresh).toHaveBeenCalled();
  });
});
