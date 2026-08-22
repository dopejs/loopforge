/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The hypothesis review surface.
 *
 * Two behaviours here exist only in this component and are the reason it is
 * a review view rather than a form: a second draft merges instead of
 * replacing, so it cannot discard edits the user already made, and missing
 * fields are marked without blocking submission, because completeness is the
 * core's judgement and not the form's.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", () => ({ isDesktopRuntime: () => true }));
// The operator now comes from the Agent, so it is answered through invoke
// like everything else rather than stubbed at the module boundary.
const OPERATOR = {
  schema_version: "loopforge-settings-v1",
  id: "op_1",
  name: "Ada",
  configured: true
};

vi.mock("../i18n", async () => {
  const { en } = await import("../i18n/locales/en");
  return {
    useI18n: () => ({
      t: (key: string, values?: Record<string, unknown>) => {
        const template = (en as Record<string, string>)[key];
        if (template === undefined) throw new Error(`missing message key: ${key}`);
        return values
          ? template.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name]))
          : template;
      }
    })
  };
});

const { HypothesisEditor } = await import("./HypothesisEditor");
const { HYPOTHESIS_FIELDS, emptyFields } = await import("../hypothesis");

/** A draft that answers only some headings, as a real model reply might. */
function partialDraft(overrides: Record<string, string> = {}) {
  return {
    schema_version: "loopforge-hypothesis-v1",
    present: false,
    draft: true,
    fields: { ...emptyFields(), platform: "Web", core_verb: "Charge", ...overrides },
    missing: []
  };
}

function fieldFor(name: string): HTMLTextAreaElement {
  // Fields render in declaration order, after the brief input.
  const index = HYPOTHESIS_FIELDS.indexOf(name as never);
  return screen.getAllByRole("textbox").filter((node) => node.tagName === "TEXTAREA")[
    index
  ] as HTMLTextAreaElement;
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("HypothesisEditor", () => {
  it("marks empty fields without blocking submission", async () => {
    invoke.mockResolvedValue({});
    render(
      <HypothesisEditor projectRoot="/p" initial={null} onClose={() => {}} onSaved={() => {}} />
    );

    // Every field starts empty, so every field is marked.
    expect(screen.getAllByText("Empty")).toHaveLength(HYPOTHESIS_FIELDS.length);
    // But the control stays live: completeness is the core's call, and a form
    // that disabled itself would be a second implementation of that rule.
    const record = screen.getByRole("button", { name: "Record hypothesis" });
    expect((record as HTMLButtonElement).disabled).toBe(false);
  });

  it("merges a second draft instead of discarding edits", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "agent_hypothesis_draft") return Promise.resolve(partialDraft());
      return Promise.resolve({});
    });
    render(
      <HypothesisEditor projectRoot="/p" initial={null} onClose={() => {}} onSaved={() => {}} />
    );

    // The user writes a field the model left blank.
    fireEvent.change(fieldFor("constraints"), { target: { value: "No networking." } });

    fireEvent.change(screen.getByPlaceholderText(/2D game where charging/), {
      target: { value: "a charge mechanic" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Draft with agent" }));

    await waitFor(() => expect(fieldFor("platform").value).toBe("Web"));
    // The edit survives: the draft filled what it answered and left the rest.
    expect(fieldFor("constraints").value).toBe("No networking.");
  });

  it("does not blank a field the second draft left empty", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "agent_hypothesis_draft") {
        return Promise.resolve(partialDraft({ platform: "   " }));
      }
      return Promise.resolve({});
    });
    render(
      <HypothesisEditor projectRoot="/p" initial={null} onClose={() => {}} onSaved={() => {}} />
    );

    fireEvent.change(fieldFor("platform"), { target: { value: "Desktop" } });
    fireEvent.change(screen.getByPlaceholderText(/2D game where charging/), {
      target: { value: "anything" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Draft with agent" }));

    await waitFor(() => expect(fieldFor("core_verb").value).toBe("Charge"));
    // Whitespace from the model is not an answer, so it must not overwrite one.
    expect(fieldFor("platform").value).toBe("Desktop");
  });

  it("submits the fields and rationale, leaving the approver to the Agent", async () => {
    invoke.mockResolvedValue({});
    const onSaved = vi.fn();
    render(
      <HypothesisEditor projectRoot="/p" initial={null} onClose={() => {}} onSaved={onSaved} />
    );

    fireEvent.change(fieldFor("hypothesis"), { target: { value: "Charging reads." } });
    const rationale = screen.getAllByRole("textbox").at(-1)!;
    fireEvent.change(rationale, { target: { value: "Reviewed the draft." } });
    fireEvent.click(screen.getByRole("button", { name: "Record hypothesis" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(([command]) => command === "agent_hypothesis_create");
      expect(call).toBeTruthy();
      const payload = (call as [string, Record<string, unknown>])[1];
      expect((payload.fields as Record<string, string>).hypothesis).toBe("Charging reads.");
      expect(payload.rationale).toBe("Reviewed the draft.");
      // The approver comes from the operator the Agent stores, so this surface
      // does not name one -- and neither does any other caller.
      expect(payload.approver_id).toBeUndefined();
      expect(payload.approver_name).toBeUndefined();
    });
  });

  it("will not draft from an empty brief", async () => {
    invoke.mockResolvedValue({});
    render(
      <HypothesisEditor projectRoot="/p" initial={null} onClose={() => {}} onSaved={() => {}} />
    );

    const draft = screen.getByRole("button", { name: "Draft with agent" });
    expect((draft as HTMLButtonElement).disabled).toBe(true);
  });
});
