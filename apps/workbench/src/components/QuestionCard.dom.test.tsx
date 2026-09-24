/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The question the agent is waiting on.
 *
 * The model used to write the choices into its reply -- "A. I'll write the
 * Unity scripts  B. you already have code  C. start implementing. Which?" --
 * and the person answered by typing "A", guessing what the letter still meant
 * to a model that had moved on. Now asking is a tool call that blocks, and
 * what they choose becomes its result.
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
      locale: "en",
      t: (key: string) => {
        const template = (en as Record<string, string>)[key];
        if (template === undefined) throw new Error(`missing message key: ${key}`);
        return template;
      }
    })
  };
});

const { QuestionCard } = await import("./QuestionCard");

function question(overrides: Record<string, unknown> = {}) {
  return {
    question_id: "ask_1",
    question: "用什么游戏引擎？",
    options: [
      { label: "Unity", value: "Unity" },
      { label: "Godot", value: "Godot" }
    ],
    allow_free_text: false,
    asked_at: "2026-09-03T05:00:00Z",
    ...overrides
  };
}

function waitingOn(...items: unknown[]) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_questions") {
      return Promise.resolve({ schema_version: "loopforge-question-v1", questions: items });
    }
    return Promise.resolve({ schema_version: "loopforge-question-v1", questions: [] });
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("QuestionCard", () => {
  it("shows nothing when nothing is being asked", async () => {
    waitingOn();
    const { container } = render(<QuestionCard projectRoot="/p" enabled />);

    await waitFor(() => expect(invoke).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("shows the question and the answers the model named", async () => {
    waitingOn(question());
    render(<QuestionCard projectRoot="/p" enabled />);

    expect(await screen.findByText("用什么游戏引擎？")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Unity" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Godot" })).toBeTruthy();
  });

  it("sends the choice back to the call that is waiting", async () => {
    // The whole point: the model is told what they picked rather than left to
    // parse a letter out of the next message.
    waitingOn(question());
    render(<QuestionCard projectRoot="/p" enabled />);

    fireEvent.click(await screen.findByRole("button", { name: "Godot" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find((entry) => entry[0] === "agent_answer_question");
      expect(call).toBeTruthy();
      const sent = call![1] as Record<string, unknown>;
      expect(sent.questionId).toBe("ask_1");
      expect(sent.answer).toBe("Godot");
    });
  });

  it("takes an answer in the person's own words when that is allowed", async () => {
    // A named option is rarely the whole of what someone means.
    waitingOn(question({ allow_free_text: true }));
    render(<QuestionCard projectRoot="/p" enabled />);

    fireEvent.change(await screen.findByPlaceholderText(/your own words/i), {
      target: { value: "先用 Godot 试试" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Answer" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find((entry) => entry[0] === "agent_answer_question");
      expect((call![1] as Record<string, unknown>).answer).toBe("先用 Godot 试试");
    });
  });

  it("offers a way to answer a question that named no options", async () => {
    // Otherwise it is a card nobody can answer.
    waitingOn(question({ options: [], allow_free_text: true }));
    render(<QuestionCard projectRoot="/p" enabled />);

    expect(await screen.findByPlaceholderText(/your own words/i)).toBeTruthy();
  });

  it("does not send an empty answer", async () => {
    // An empty string would release the call with nothing, and the model would
    // read it as an answer.
    waitingOn(question({ allow_free_text: true }));
    render(<QuestionCard projectRoot="/p" enabled />);
    await screen.findByPlaceholderText(/your own words/i);

    expect(screen.getByRole("button", { name: "Answer" }).hasAttribute("disabled")).toBe(true);
  });

  it("keeps asking while a turn is running", async () => {
    // The question appears mid-turn; reading once on mount would show nothing.
    waitingOn();
    render(<QuestionCard projectRoot="/p" enabled />);
    await waitFor(() => expect(invoke).toHaveBeenCalled());

    waitingOn(question());

    expect(await screen.findByText("用什么游戏引擎？", {}, { timeout: 4000 })).toBeTruthy();
  });

  it("stops asking once the panel is not enabled", async () => {
    waitingOn(question());
    render(<QuestionCard projectRoot="/p" enabled={false} />);

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(invoke).not.toHaveBeenCalled();
  });

  it("does not leave the buttons live after an answer", async () => {
    waitingOn(question());
    render(<QuestionCard projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Unity" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Unity" })).toBeNull());
  });
});
