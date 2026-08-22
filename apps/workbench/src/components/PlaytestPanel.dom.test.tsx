/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The playtest surface, where the product's honesty rules become interface.
 *
 * Two of them cannot be checked by any pure-module test: that consent starts
 * unanswered on screen, and that the controls are absent rather than failing
 * when the stage does not allow this work. Both are claims the UI makes about
 * a real person and a real project state.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", () => ({ isDesktopRuntime: () => true }));

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

const { PlaytestPanel } = await import("./PlaytestPanel");

function state(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "loopforge-playtest-v1",
    stage: "PLAYTEST_REQUIRED",
    allowed: true,
    protocol: null,
    consent_values: ["obtained", "not_required"],
    fields: [],
    list_fields: [],
    ...overrides
  };
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("PlaytestPanel", () => {
  it("explains the stage requirement instead of offering a control that fails", async () => {
    invoke.mockResolvedValue(state({ stage: "DISCOVERY", allowed: false }));

    render(<PlaytestPanel projectRoot="/p" />);

    expect(
      await screen.findByText(/recorded once the prototype reaches the playtest stage/)
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Write protocol" })).toBeNull();
  });

  it("offers the report only once a protocol exists", async () => {
    invoke.mockResolvedValue(
      state({ protocol: { protocol_id: "plt_1", created_at: "2026-08-22T00:00:00Z" } })
    );

    render(<PlaytestPanel projectRoot="/p" />);

    expect(await screen.findByRole("button", { name: "Enter report" })).toBeTruthy();
  });

  it("leaves consent unanswered until a person answers it", async () => {
    invoke.mockResolvedValue(
      state({ protocol: { protocol_id: "plt_1", created_at: "2026-08-22T00:00:00Z" } })
    );

    render(<PlaytestPanel projectRoot="/p" />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter report" }));

    const obtained = await screen.findByRole("button", { name: "Consent obtained" });
    const notRequired = screen.getByRole("button", { name: "Not required" });
    // Neither is pre-selected. A default here would record a claim about a
    // real person that nobody made.
    expect(obtained.getAttribute("aria-pressed")).toBe("false");
    expect(notRequired.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(obtained);
    expect(obtained.getAttribute("aria-pressed")).toBe("true");
    expect(notRequired.getAttribute("aria-pressed")).toBe("false");
  });

  it("sends observations and interpretation as separate fields", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "agent_playtest") {
        return Promise.resolve(
          state({ protocol: { protocol_id: "plt_1", created_at: "2026-08-22T00:00:00Z" } })
        );
      }
      if (command === "agent_playtest_report") return Promise.resolve(state());
      throw new Error(`unexpected command: ${command}`);
    });

    render(<PlaytestPanel projectRoot="/p" />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter report" }));
    fireEvent.click(await screen.findByRole("button", { name: "Consent obtained" }));

    const textareas = screen.getAllByRole("textbox");
    // participant_context, then the five lists, then two texts, then interpretation.
    fireEvent.change(textareas[1], { target: { value: "charged twice\ndied once" } });
    fireEvent.change(textareas[textareas.length - 1], {
      target: { value: "the trade-off reads" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Import report" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(([command]) => command === "agent_playtest_report");
      expect(call).toBeTruthy();
      const report = (call as [string, { report: Record<string, unknown> }])[1].report;
      expect(report.raw_observations).toEqual(["charged twice", "died once"]);
      expect(report.interpretation).toBe("the trade-off reads");
      expect(report.consent_status).toBe("obtained");
    });
  });
});
