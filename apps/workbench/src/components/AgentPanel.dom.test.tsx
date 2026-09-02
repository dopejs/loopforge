/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

/**
 * Which side of the transcript is Markdown.
 *
 * The Agent writes Markdown and the user writes whatever they meant. Passing
 * both through a renderer would reinterpret the one person here who did not
 * mean any of it as markup: a filename with underscores would come back
 * italicised, and a line beginning `- ` would become a list they did not write.
 */

const invoke = vi.hoisted(() => vi.fn(() => Promise.resolve()));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

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

// jsdom implements no scrolling, and the transcript scrolls to its end on
// every update. Not a stub for behaviour under test -- without it the render
// throws before any assertion runs.
Element.prototype.scrollIntoView = (): void => {};

const { Transcript } = await import("./AgentPanel");

function entry(author: "user" | "agent", text: string) {
  return { id: `${author}-1`, author, text };
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("Transcript", () => {
  it("renders the Agent's reply as Markdown", () => {
    render(
      <Transcript
        transcript={[entry("agent", "State: **UNINITIALIZED**")]}
        busy={false}
        variant="page"
      />
    );

    expect(screen.getByText("UNINITIALIZED").tagName).toBe("STRONG");
  });

  it("shows the user's own message exactly as they typed it", () => {
    const typed = "why does **this** show _underscores_ in my_file_name?";
    render(<Transcript transcript={[entry("user", typed)]} busy={false} variant="page" />);

    expect(screen.getByText(typed)).toBeTruthy();
    expect(document.querySelector("strong")).toBeNull();
    expect(document.querySelector("em")).toBeNull();
  });

  it("keeps a failed entry readable rather than parsing the error", () => {
    render(
      <Transcript
        transcript={[{ ...entry("agent", "HTTP 400: bad **request**"), failed: true }]}
        busy={false}
        variant="page"
      />
    );

    // A failure is still the Agent speaking, so it renders the same way; what
    // matters is that the entry keeps its failed styling hook.
    expect(document.querySelector(".message.failed")).not.toBeNull();
  });

  it("sends a suggestion rather than typing it into the box", async () => {
    // Clicking one is the person deciding to ask it. Filling the composer
    // instead would leave them to press send on a sentence they did not write,
    // which is a worse version of an empty box.
    const sent = vi.fn();
    render(
      <Transcript transcript={[]} busy={false} variant="page" stage="DISCOVERY" onSuggest={sent} />
    );

    const suggestion = screen.getByText(/turn my idea into something we can test/i);
    fireEvent.click(suggestion);

    expect(sent).toHaveBeenCalledWith(
      "Help me turn my idea into something we can test"
    );
  });

  it("offers what the stage makes worth asking", () => {
    // A person in PROTOTYPING is not asking the same question as one who has
    // just opened an empty folder.
    render(
      <Transcript transcript={[]} busy={false} variant="page" stage="PROTOTYPING" onSuggest={() => {}} />
    );

    expect(screen.getByText(/Build the project/)).toBeTruthy();
    expect(screen.queryByText(/Set this folder up/)).toBeNull();
  });

  it("offers nothing when the Agent cannot answer", () => {
    // A suggestion that does nothing on click is worse than no suggestion.
    render(<Transcript transcript={[]} busy={false} variant="page" stage="DISCOVERY" />);

    expect(screen.queryByText(/turn my idea/i)).toBeNull();
  });
});
