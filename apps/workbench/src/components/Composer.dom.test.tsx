/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The box people type in.
 *
 * Two things it got wrong, and both of them on every message rather than in
 * some corner: Enter sent while an input method was still composing, so anyone
 * writing Chinese, Japanese or Korean sent a fragment each time they picked a
 * candidate; and `@` was a chip that inserted three characters and left the
 * person to type a path from memory.
 */

const invoke = vi.hoisted(() =>
  vi.fn((_command: string, _args?: unknown): Promise<unknown> => Promise.resolve([]))
);
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

const { Composer, mentionAt } = await import("./AgentPanel");

afterEach(() => {
  cleanup();
  invoke.mockReset();
  invoke.mockImplementation(() => Promise.resolve([]));
});

function box() {
  return screen.getByRole("textbox");
}

describe("Composer", () => {
  it("sends on Enter", () => {
    const sent = vi.fn();
    render(<Composer disabled={false} busy={false} onSend={sent} />);
    fireEvent.change(box(), { target: { value: "hello" } });

    fireEvent.keyDown(box(), { key: "Enter" });

    expect(sent).toHaveBeenCalledWith("hello");
  });

  it("does not send while an input method is composing", () => {
    // Enter confirms a candidate. Sending here means every message a Chinese,
    // Japanese or Korean writer types goes out as a fragment of its first word.
    const sent = vi.fn();
    render(<Composer disabled={false} busy={false} onSend={sent} />);
    fireEvent.change(box(), { target: { value: "ni" } });

    fireEvent.keyDown(box(), { key: "Enter", isComposing: true });

    expect(sent).not.toHaveBeenCalled();
  });

  it("does not send on the keydown that ends a composition", () => {
    // The platform webview on macOS is WKWebView, where `compositionend` fires
    // after this keydown -- so a flag set by the events alone is already false
    // and would let it through.
    const sent = vi.fn();
    render(<Composer disabled={false} busy={false} onSend={sent} />);
    fireEvent.compositionStart(box());
    fireEvent.change(box(), { target: { value: "你好" } });

    fireEvent.keyDown(box(), { key: "Enter" });

    expect(sent).not.toHaveBeenCalled();
  });

  it("sends once composition has ended", () => {
    const sent = vi.fn();
    render(<Composer disabled={false} busy={false} onSend={sent} />);
    fireEvent.compositionStart(box());
    fireEvent.change(box(), { target: { value: "你好" } });
    fireEvent.compositionEnd(box());

    fireEvent.keyDown(box(), { key: "Enter" });

    expect(sent).toHaveBeenCalledWith("你好");
  });

  it("keeps Shift+Enter as a newline", () => {
    const sent = vi.fn();
    render(<Composer disabled={false} busy={false} onSend={sent} />);
    fireEvent.change(box(), { target: { value: "one" } });

    fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });

    expect(sent).not.toHaveBeenCalled();
  });

  it("offers the project's files while an @ is being typed", async () => {
    invoke.mockImplementation(() => Promise.resolve(["main.gd", "scenes/main.tscn"]));
    render(<Composer disabled={false} busy={false} projectRoot="/p" onSend={() => {}} />);

    fireEvent.change(box(), { target: { value: "look at @mai" } });

    expect(await screen.findByText("main.gd")).toBeTruthy();
    const call = invoke.mock.calls.find((entry) => entry[0] === "project_files");
    expect((call![1] as Record<string, unknown>).query).toBe("mai");
  });

  it("replaces the mention rather than appending to the message", async () => {
    invoke.mockImplementation(() => Promise.resolve(["main.gd"]));
    render(<Composer disabled={false} busy={false} projectRoot="/p" onSend={() => {}} />);
    fireEvent.change(box(), { target: { value: "look at @mai" } });
    fireEvent.mouseDown(await screen.findByText("main.gd"));

    await waitFor(() =>
      expect((box() as HTMLTextAreaElement).value).toBe("look at @main.gd ")
    );
  });

  it("completes on Enter without also sending the message", async () => {
    // Both are bound to Enter. Completing and sending in one keystroke would
    // send a message the person was still assembling.
    invoke.mockImplementation(() => Promise.resolve(["main.gd"]));
    const sent = vi.fn();
    render(<Composer disabled={false} busy={false} projectRoot="/p" onSend={sent} />);
    fireEvent.change(box(), { target: { value: "look at @mai" } });
    await screen.findByText("main.gd");

    fireEvent.keyDown(box(), { key: "Enter" });

    expect(sent).not.toHaveBeenCalled();
    await waitFor(() =>
      expect((box() as HTMLTextAreaElement).value).toBe("look at @main.gd ")
    );
  });
});

describe("mentionAt", () => {
  it("finds the mention the caret is inside", () => {
    expect(mentionAt("look at @mai", 12)).toEqual({ start: 8, query: "mai" });
  });

  it("is not an email address", () => {
    // `user@host` is not someone asking for a file.
    expect(mentionAt("mail me at john@example.com", 27)).toBeNull();
  });

  it("ends at a space", () => {
    // The mention is over; completing here would rewrite words already typed.
    expect(mentionAt("@main.gd and then", 17)).toBeNull();
  });

  it("is nothing when there is no @ before the caret", () => {
    expect(mentionAt("plain words", 5)).toBeNull();
  });
});
