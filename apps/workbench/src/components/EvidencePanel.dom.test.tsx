/**
 * @vitest-environment jsdom
 *
 * Declared per file rather than in the config: only component suites need a
 * DOM, and the pure-module suites stay on the faster node environment.
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * Component tests for the evidence surface.
 *
 * The pure-module suites cannot reach the behaviour that actually bites here:
 * that cancelling the file picker is not an error, that a file outside the
 * project is labelled as linked rather than held, and that trust level reaches
 * the screen at all. Each of those is a claim the UI makes about what the core
 * did, and a wrong one misrepresents the evidence record.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", () => ({ isDesktopRuntime: () => true }));

// The real catalogue, so a missing key fails here rather than rendering blank.
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

const { EvidencePanel } = await import("./EvidencePanel");

function evidence(overrides: Record<string, unknown> = {}) {
  return {
    id: "evd_1",
    type: "capture",
    result: "observation",
    trust_level: "manually_imported",
    producer: "local-screenshot-import",
    created_at: "2026-08-22T00:00:00Z",
    path: "shot.png",
    path_kind: "project-relative",
    ...overrides
  };
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("EvidencePanel", () => {
  it("shows the trust level, which is what separates a tool from a person", async () => {
    invoke.mockImplementation((command: string) =>
      command === "agent_evidence"
        ? Promise.resolve({
            evidence: [evidence(), evidence({ id: "evd_2", type: "build", result: "passed", trust_level: "tool_generated", path: "run.json" })]
          })
        : Promise.resolve(null)
    );

    render(<EvidencePanel projectRoot="/p" />);

    expect(await screen.findByText("imported")).toBeTruthy();
    expect(screen.getByText("from a tool")).toBeTruthy();
  });

  it("marks a file outside the project as linked rather than held", async () => {
    invoke.mockImplementation((command: string) =>
      command === "agent_evidence"
        ? Promise.resolve({ evidence: [evidence({ path: "/elsewhere/shot.png", path_kind: "absolute" })] })
        : Promise.resolve(null)
    );

    render(<EvidencePanel projectRoot="/p" />);

    const row = await screen.findByText(/\/elsewhere\/shot\.png/);
    expect(row.textContent).toContain("linked, not copied");
  });

  it("treats a cancelled picker as nothing happening", async () => {
    const onRegistered = vi.fn();
    invoke.mockImplementation((command: string) => {
      if (command === "agent_evidence") return Promise.resolve({ evidence: [] });
      if (command === "select_capture_file") return Promise.resolve(null);
      throw new Error(`unexpected command: ${command}`);
    });

    render(<EvidencePanel projectRoot="/p" onRegistered={onRegistered} />);
    (await screen.findByRole("button", { name: "Register screenshot" })).click();

    await waitFor(() => expect(invoke).toHaveBeenCalledWith("select_capture_file"));
    // Asserted directly rather than inferred: registering nothing would also
    // leave onRegistered uncalled, and the mock's throw is swallowed by the
    // component's own error handling. Only this catches the real defect --
    // verified by deleting the guard and watching this line fail.
    expect(
      invoke.mock.calls.some(([command]) => command === "agent_capture")
    ).toBe(false);
    expect(onRegistered).not.toHaveBeenCalled();
    // And the user is shown no error for a choice they made.
    expect(screen.queryByText(/could not be registered/)).toBeNull();
  });

  it("registers the chosen file and reports it upward", async () => {
    const onRegistered = vi.fn();
    invoke.mockImplementation((command: string) => {
      if (command === "agent_evidence") return Promise.resolve({ evidence: [] });
      if (command === "select_capture_file") return Promise.resolve("/p/shot.png");
      if (command === "agent_capture") return Promise.resolve({ evidence: evidence() });
      throw new Error(`unexpected command: ${command}`);
    });

    render(<EvidencePanel projectRoot="/p" onRegistered={onRegistered} />);
    (await screen.findByRole("button", { name: "Register screenshot" })).click();

    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith("agent_capture", {
        projectPath: "/p",
        path: "/p/shot.png"
      })
    );
    // The claim above this panel derives from evidence, so it has to be told.
    await waitFor(() => expect(onRegistered).toHaveBeenCalled());
  });

  it("surfaces a failure instead of silently doing nothing", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "agent_evidence") return Promise.resolve({ evidence: [] });
      if (command === "select_capture_file") return Promise.resolve("/p/shot.png");
      return Promise.reject(new Error("evidence file is missing"));
    });

    render(<EvidencePanel projectRoot="/p" />);
    (await screen.findByRole("button", { name: "Register screenshot" })).click();

    expect(await screen.findByText(/evidence file is missing/)).toBeTruthy();
  });
});
