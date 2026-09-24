/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * The generated suggestions, layered over the fixed list.
 *
 * The fixed list is instant, needs no provider, and is never wrong -- only
 * generic. The Agent writes a better one, grounded in this project and in the
 * reader's language, and it arrives seconds later or not at all. What must
 * never happen is a spinner or a gap: a person opening an empty chat has
 * something to click in the first frame either way.
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
      locale: "zh-Hans",
      t: (key: string) => {
        const template = (en as Record<string, string>)[key];
        if (template === undefined) throw new Error(`missing message key: ${key}`);
        return template;
      }
    })
  };
});

Element.prototype.scrollIntoView = (): void => {};

const { Transcript } = await import("./AgentPanel");

/** Answers `agent_suggestions` with a script, one reply per call. */
function answers(...replies: unknown[]) {
  let call = 0;
  invoke.mockImplementation((command: string) => {
    if (command !== "agent_suggestions") return Promise.resolve({});
    const reply = replies[Math.min(call, replies.length - 1)];
    call += 1;
    return reply instanceof Error ? Promise.reject(reply) : Promise.resolve(reply);
  });
}

function generated(suggestions: string[], generating = false) {
  return { schema_version: "loopforge-suggestion-v1", suggestions, generating };
}

function draw(stage = "DISCOVERY") {
  return render(
    <Transcript
      transcript={[]}
      busy={false}
      variant="page"
      stage={stage}
      projectRoot="/p"
      onSuggest={() => {}}
    />
  );
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("generated suggestions", () => {
  it("shows the fixed list before anything has been generated", async () => {
    // The first frame. Waiting on the model here would leave an empty chat
    // that says "how can I help?" and offers nothing, which is where this
    // started.
    answers(generated([], true));
    draw();

    expect(screen.getByText(/turn my idea into something we can test/i)).toBeTruthy();
  });

  it("replaces it with what the model wrote about this project", async () => {
    answers(generated(["接着验证跳跃手感", "先跑一次构建"]));
    draw();

    expect(await screen.findByText("接着验证跳跃手感")).toBeTruthy();
    // And the generic one is gone rather than listed beneath: two sets of
    // suggestions is a menu, and the specific one is strictly better.
    expect(screen.queryByText(/turn my idea into something we can test/i)).toBeNull();
  });

  it("asks in the language the window is reading", async () => {
    // Generated text cannot be translated, so the locale has to travel with
    // the read.
    answers(generated([]));
    draw();

    await waitFor(() => {
      const call = invoke.mock.calls.find((entry) => entry[0] === "agent_suggestions");
      expect((call![1] as Record<string, unknown>).locale).toBe("zh-Hans");
    });
  });

  it("keeps looking while one is being written", async () => {
    // The turn-end generation lands seconds after the conversation is opened.
    answers(generated([], true), generated(["接着验证跳跃手感"]));
    draw();

    expect(await screen.findByText("接着验证跳跃手感", {}, { timeout: 6000 })).toBeTruthy();
  });

  it("stops looking once nothing is being written", async () => {
    // A runtime that is down reports no generation. Polling it would ask
    // forever for an answer nobody is preparing.
    answers(generated([], false));
    draw();

    await waitFor(() => expect(invoke).toHaveBeenCalled());
    const asked = invoke.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 4000));

    expect(invoke.mock.calls.length).toBe(asked);
  }, 10000);

  it("keeps the fixed list when the Agent cannot answer", async () => {
    // Not started yet, most likely. There is nothing to report and nothing to
    // retry -- the generic list is a complete answer on its own.
    answers(new Error("Loopforge Agent has not been started"));
    draw();

    await waitFor(() => expect(invoke).toHaveBeenCalled());
    expect(screen.getByText(/turn my idea into something we can test/i)).toBeTruthy();
  });

  it("goes back to the fixed list when the project changes", async () => {
    // Suggestions describe one project. Carrying them to the next one would
    // confidently propose work that belongs somewhere else.
    answers(generated(["接着验证跳跃手感"]));
    const view = draw();
    await screen.findByText("接着验证跳跃手感");

    invoke.mockImplementation(() => Promise.resolve(generated([], true)));
    view.rerender(
      <Transcript
        transcript={[]}
        busy={false}
        variant="page"
        stage="DISCOVERY"
        projectRoot="/other"
        onSuggest={() => {}}
      />
    );

    expect(screen.queryByText("接着验证跳跃手感")).toBeNull();
  });
});
