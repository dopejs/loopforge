/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The decision surface.
 *
 * Two properties here are product positions rather than implementation
 * details, and neither is checkable without rendering: that the three outcomes
 * are offered as equals, and that a `keep` which does not cite the playtest is
 * warned about before it is attempted rather than after the core refuses it.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", () => ({ isDesktopRuntime: () => true }));
vi.mock("../operator", async () => {
  const actual = await vi.importActual<typeof import("../operator")>("../operator");
  return { ...actual, loadOperator: () => ({ id: "op_1", name: "Ada" }) };
});

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

const { DecisionPanel } = await import("./DecisionPanel");

const EVIDENCE = [
  {
    id: "evd_play",
    type: "playtest",
    result: "observation",
    trust_level: "human_attested",
    producer: "local-playtest-import",
    created_at: "2026-08-22T00:00:00Z",
    path: "report.json",
    path_kind: "project-relative"
  },
  {
    id: "evd_build",
    type: "build",
    result: "passed",
    trust_level: "tool_generated",
    producer: "loopforge.adapter.godot",
    created_at: "2026-08-22T00:00:00Z",
    path: "run.json",
    path_kind: "project-relative"
  }
];

function mockAgent(overrides: Record<string, unknown> = {}) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_decision") {
      return Promise.resolve({
        schema_version: "loopforge-decision-v1",
        stage: "PROTOTYPE_DECISION",
        allowed: true,
        decisions: ["keep", "kill", "refactor"],
        playtest_evidence_ids: ["evd_play"],
        recorded: null,
        ...overrides
      });
    }
    if (command === "agent_evidence") return Promise.resolve({ evidence: EVIDENCE });
    if (command === "agent_hypothesis") {
      return Promise.resolve({
        schema_version: "loopforge-hypothesis-v1",
        present: true,
        revision: 1,
        fields: Object.fromEntries(
          [
            "intended_player", "platform", "player_fantasy", "core_verb",
            "moment_to_moment_loop", "hypothesis", "constraints", "non_goals",
            "cheapest_validation", "keep_signals", "kill_signals"
          ].map((key) => [key, `value ${key}`])
        ),
        missing: []
      });
    }
    if (command === "agent_decide") return Promise.resolve({ decision: "keep", stage: "VERTICAL_SLICE" });
    throw new Error(`unexpected command: ${command}`);
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

async function openDialog(): Promise<void> {
  render(<DecisionPanel projectRoot="/p" />);
  fireEvent.click(await screen.findByRole("button", { name: "Decide" }));
}

describe("DecisionPanel", () => {
  it("offers the three outcomes with the same control and none preselected", async () => {
    mockAgent();
    await openDialog();

    const outcomes = await Promise.all(
      ["Keep", "Kill", "Refactor"].map((label) =>
        screen.findByRole("button", { name: new RegExp(`^${label}`) })
      )
    );
    // Same class means the same visual weight: nothing marks one as the
    // expected answer.
    const classes = new Set(outcomes.map((node) => node.className));
    expect(classes).toEqual(new Set(["decision-choice"]));
    for (const node of outcomes) {
      expect(node.getAttribute("aria-pressed")).toBe("false");
    }
  });

  it("warns that a keep must cite the playtest, before it is attempted", async () => {
    mockAgent();
    await openDialog();

    fireEvent.click(await screen.findByRole("button", { name: /^Keep/ }));

    const warning = await screen.findByText(/must cite the playtest report/);
    expect(warning).toBeTruthy();

    // Citing it clears the warning; citing the build alone would not.
    fireEvent.click(screen.getByRole("checkbox", { name: /report\.json/ }));
    await waitFor(() =>
      expect(screen.queryByText(/must cite the playtest report/)).toBeNull()
    );
  });

  it("does not warn for outcomes that carry no such requirement", async () => {
    mockAgent();
    await openDialog();

    fireEvent.click(await screen.findByRole("button", { name: /^Kill/ }));

    expect(screen.queryByText(/must cite the playtest report/)).toBeNull();
  });

  it("shows each item's trust level so a citation is an informed one", async () => {
    mockAgent();
    await openDialog();

    expect(await screen.findByText("attested")).toBeTruthy();
    expect(screen.getByText("from a tool")).toBeTruthy();
  });

  it("seeds a refactor from the current hypothesis rather than a blank form", async () => {
    mockAgent();
    await openDialog();

    fireEvent.click(await screen.findByRole("button", { name: /^Refactor/ }));

    // A refactor is a change to the question, not a restart.
    const seeded = await screen.findAllByDisplayValue("value hypothesis");
    expect(seeded.length).toBeGreaterThan(0);
  });

  it("sends the citation, approver and rationale together", async () => {
    mockAgent();
    await openDialog();

    fireEvent.click(await screen.findByRole("button", { name: /^Kill/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /run\.json/ }));
    const rationale = screen.getAllByRole("textbox").at(-1)!;
    fireEvent.change(rationale, { target: { value: "Out of scope for this budget." } });
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(([command]) => command === "agent_decide");
      expect(call).toBeTruthy();
      const payload = (call as [string, Record<string, unknown>])[1];
      expect(payload.decision).toBe("kill");
      expect(payload.evidenceIds).toEqual(["evd_build"]);
      expect(payload.approverName).toBe("Ada");
      expect(payload.rationale).toBe("Out of scope for this budget.");
    });
  });

  it("stays hidden when the stage does not allow a decision", async () => {
    mockAgent({ stage: "PROTOTYPING", allowed: false });
    render(<DecisionPanel projectRoot="/p" />);
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("agent_decision", { projectPath: "/p" }));
    expect(screen.queryByRole("button", { name: "Decide" })).toBeNull();
  });
});
