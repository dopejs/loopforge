/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

/**
 * Rendering the Agent's replies.
 *
 * The transcript printed the reply as a plain text node, so every heading,
 * list and code span the model wrote arrived as literal punctuation -- a user
 * read `**UNINITIALIZED**` and `- ` on screen. These pin that it is rendered,
 * and the two things that must not follow from rendering it: model-authored
 * HTML reaching the DOM, and a model-authored link navigating the window the
 * application is drawn in.
 */

// Resolves, because the real `invoke` returns a promise and the component
// attaches to it. A mock returning `undefined` throws inside the click
// handler, which the test would otherwise swallow and report as a pass.
const invoke = vi.hoisted(() => vi.fn(() => Promise.resolve()));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

const { Markdown, isSafeHref } = await import("./Markdown");

afterEach(() => {
  cleanup();
  invoke.mockReset();
  invoke.mockImplementation(() => Promise.resolve());
});

describe("Markdown", () => {
  it("renders emphasis, lists and code as elements rather than punctuation", () => {
    render(
      <Markdown>{"State: **UNINITIALIZED**\n\n- run `loopforge init`\n- then plan"}</Markdown>
    );

    expect(screen.getByText("UNINITIALIZED").tagName).toBe("STRONG");
    expect(screen.getByText("loopforge init").tagName).toBe("CODE");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    // The markers themselves are gone, not merely styled around.
    expect(document.body.textContent).not.toContain("**");
    expect(document.body.textContent).not.toContain("- run");
  });

  it("renders a fenced block as preformatted code", () => {
    render(<Markdown>{"```\nloopforge status\n```"}</Markdown>);

    const code = screen.getByText(/loopforge status/);
    expect(code.closest("pre")).not.toBeNull();
  });

  it("renders GFM tables, which a model writes without being asked", () => {
    render(<Markdown>{"| a | b |\n| - | - |\n| 1 | 2 |"}</Markdown>);

    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
  });

  it("does not put model-authored HTML into the document", () => {
    // `rehype-raw` is deliberately absent. The text arrives from a model over
    // a network; nothing downstream of here is a trust boundary.
    render(<Markdown>{'<img src=x onerror="alert(1)"> <b>bold?</b>'}</Markdown>);

    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
  });

  it("opens a link externally instead of navigating the application", () => {
    // The shell is the application's own window. Letting an href navigate it
    // would replace the Workbench with a web page and leave no way back.
    render(<Markdown>{"[docs](https://example.test/docs)"}</Markdown>);

    const link = screen.getByText("docs");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    fireEvent(link, click);

    expect(click.defaultPrevented).toBe(true);
    expect(invoke).toHaveBeenCalledWith("open_external", {
      url: "https://example.test/docs"
    });
  });

  it("does not make a link out of a scheme it will not open", () => {
    // Pins the end-to-end property, not this file's contribution to it:
    // `react-markdown` blanks an unsafe protocol in `defaultUrlTransform`
    // before the component sees it, so this passes with our own check removed.
    // The case only our check covers is below.
    render(<Markdown>{"[click me](javascript:alert(1))"}</Markdown>);

    const rendered = screen.getByText("click me");
    expect(rendered.tagName).not.toBe("A");
    expect(document.querySelector("a")).toBeNull();

    fireEvent.click(rendered);
    expect(invoke).not.toHaveBeenCalled();
  });

  it("does not make a link out of a path with nowhere to resolve against", () => {
    // `defaultUrlTransform` passes a relative URL through untouched -- it has
    // no protocol to object to. In a browser that resolves against the page;
    // in a desktop shell there is no such document, and `open_external`
    // refuses anything that is not http(s). So it would be a link that always
    // fails on click. This is the case our own check exists for.
    render(<Markdown>{"[report](/etc/passwd)"}</Markdown>);

    expect(screen.getByText("report").tagName).not.toBe("A");
    expect(document.querySelector("a")).toBeNull();
  });

  it("judges a scheme rather than searching the string for one", () => {
    // A substring check would accept `https://evil.test#javascript:` and
    // reject a legitimate URL containing the word.
    expect(isSafeHref("https://example.test/a?q=javascript:x")).toBe(true);
    expect(isSafeHref("mailto:someone@example.test")).toBe(true);
    expect(isSafeHref("javascript:alert(1)")).toBe(false);
    expect(isSafeHref("JavaScript:alert(1)")).toBe(false);
    expect(isSafeHref("data:text/html,<script>")).toBe(false);
    expect(isSafeHref("file:///etc/passwd")).toBe(false);
    expect(isSafeHref("/relative/path")).toBe(false);
    expect(isSafeHref("")).toBe(false);
    // `react-markdown` permits these; the shell cannot open them, so a link
    // made of one would refuse on click.
    expect(isSafeHref("irc://example.test/room")).toBe(false);
    expect(isSafeHref("xmpp:someone@example.test")).toBe(false);
  });

  it("renders a half-written document without failing", () => {
    // Replies stream, so every intermediate prefix is rendered: an unclosed
    // fence and a dangling emphasis are normal states, not malformed input.
    for (const partial of ["**bold", "```\ncode", "| a | b", "- item\n- "]) {
      const view = render(<Markdown>{partial}</Markdown>);
      expect(view.container.textContent).not.toBe("");
      view.unmount();
    }
  });
});
