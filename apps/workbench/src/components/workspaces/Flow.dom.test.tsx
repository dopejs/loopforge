/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The stage machine surface.
 *
 * The property worth testing here is the one that only exists on screen: the
 * early decision reason appears where it applies, has no default, and once
 * chosen becomes part of the gate question rather than being held back until
 * the advance.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../../agent", () => ({ isDesktopRuntime: () => true }));
vi.mock("../../operator", async () => {
  const actual = await vi.importActual<typeof import("../../operator")>("../../operator");
  return { ...actual, loadOperator: () => ({ id: "op_1", name: "Ada" }) };
});

vi.mock("../../i18n", async () => {
  const { en } = await import("../../i18n/locales/en");
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

const { FlowWorkspace } = await import("./Flow");

function mockAgent(stage: string, nextStages: string[]) {
  invoke.mockImplementation((command: string, args: Record<string, unknown>) => {
    if (command === "agent_project_status") {
      return Promise.resolve({
        schema_version: "loopforge-project-status-v1",
        initialized: true,
        stage,
        claims: []
      });
    }
    if (command === "agent_gate") {
      const answered = Boolean(args.reason);
      return Promise.resolve({
        schema_version: "loopforge-gate-v1",
        gate: args.stage,
        from_stage: stage,
        result: answered ? "pass" : "blocked",
        requirements: [
          {
            code: "EARLY_DECISION_REASON",
            status: answered ? "satisfied" : "missing",
            message: "An early decision reason must be technical, scope, or abandon.",
            evidence_ids: []
          }
        ],
        next_stages: nextStages
      });
    }
    if (command === "agent_advance") {
      return Promise.resolve({ from_stage: stage, to_stage: args.stage });
    }
    throw new Error(`unexpected command: ${command}`);
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("FlowWorkspace", () => {
  it("does not ask for a reason where the transition takes none", async () => {
    mockAgent("DISCOVERY", ["PROTOTYPING"]);

    render(<FlowWorkspace projectRoot="/p" />);

    await screen.findByText("Prototyping");
    // Discovery → prototyping carries no reason; offering one would imply the
    // record will say something it will not.
    expect(screen.queryByRole("button", { name: "Scope" })).toBeNull();
  });

  it("offers the three reasons with none preselected on the early path", async () => {
    mockAgent("PROTOTYPING", ["PLAYTEST_REQUIRED", "PROTOTYPE_DECISION"]);

    render(<FlowWorkspace projectRoot="/p" />);
    // Stage nodes are disabled until the gate reports which successors are
    // legal, so clicking before that is a no-op.
    const decision = await screen.findByRole("button", { name: /^Decision/ });
    await waitFor(() => expect((decision as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(decision);

    const reasons = await Promise.all(
      ["Technical", "Scope", "Abandon"].map((label) =>
        screen.findByRole("button", { name: label })
      )
    );
    // The reason is written into the event log and shapes how the project's
    // ending reads, so nothing is chosen for the user.
    for (const node of reasons) {
      expect(node.getAttribute("aria-pressed")).toBe("false");
    }
  });

  it("re-asks the gate with the reason once it is chosen", async () => {
    mockAgent("PROTOTYPING", ["PLAYTEST_REQUIRED", "PROTOTYPE_DECISION"]);

    render(<FlowWorkspace projectRoot="/p" />);
    const decision = await screen.findByRole("button", { name: /^Decision/ });
    await waitFor(() => expect((decision as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(decision);
    expect(await screen.findByText("Missing")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Scope" }));

    // The gate tests the reason it is given, so holding it back until the
    // advance would leave the checklist reporting a requirement as unmet that
    // the advance immediately satisfies.
    await waitFor(() => {
      const call = invoke.mock.calls
        .filter(([command]) => command === "agent_gate")
        .at(-1);
      expect((call as [string, Record<string, unknown>])[1].reason).toBe("scope");
    });
    expect(await screen.findByText("Met")).toBeTruthy();
  });
});
