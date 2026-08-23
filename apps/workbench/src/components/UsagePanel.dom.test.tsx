/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * The subscription usage panel.
 *
 * The thing worth pinning is what it does with an account it has no figure
 * for. Loopforge borrows a signed-in CLI rather than holding a credential, so
 * one account reports real windows and the other reports nothing at all -- and
 * an unknown drawn as an empty bar is indistinguishable from a genuinely
 * unused one, which is the misreading these tests exist to prevent.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", () => ({ isDesktopRuntime: () => true }));

vi.mock("../i18n", async () => {
  const { en } = await import("../i18n/locales/en");
  return {
    useI18n: () => ({
      locale: "en",
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

const { UsagePanel } = await import("./UsagePanel");

function report(accounts: unknown[]) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_account_usage") {
      return Promise.resolve({ schema_version: "loopforge-account-usage-v1", accounts });
    }
    throw new Error(`unexpected command: ${command}`);
  });
}

function codex(overrides: Record<string, unknown> = {}) {
  return {
    provider_id: "codex_managed",
    available: true,
    reason: "",
    observed_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
    plan: "prolite",
    limit_id: "codex",
    windows: [
      {
        label: "5h",
        window_minutes: 300,
        used_percent: 6,
        resets_at: new Date(Date.now() + 2 * 3600_000).toISOString()
      },
      {
        label: "7d",
        window_minutes: 10080,
        used_percent: 75,
        resets_at: new Date(Date.now() + 4 * 86400_000).toISOString()
      }
    ],
    credit_balance: "",
    credits_unlimited: false,
    ...overrides
  };
}

const claudeUnavailable = {
  provider_id: "claude_managed",
  available: false,
  reason: "Claude Code records no limit windows locally.",
  observed_at: "",
  plan: "",
  limit_id: "",
  windows: [],
  credit_balance: "",
  credits_unlimited: false
};

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("UsagePanel", () => {
  it("shows each window as a reading with its own reset", async () => {
    report([codex()]);
    render(<UsagePanel projectRoot="/p" />);

    expect(await screen.findByText(/6% used/)).toBeTruthy();
    expect(screen.getByText(/75% used/)).toBeTruthy();
    // Named by duration, so the two are told apart by more than position.
    expect(screen.getByRole("meter", { name: "5 hours" })).toBeTruthy();
    expect(screen.getByRole("meter", { name: "7 days" })).toBeTruthy();
  });

  it("draws no bar for an account it has no figure for", async () => {
    report([codex(), claudeUnavailable]);
    render(<UsagePanel projectRoot="/p" />);

    await screen.findByText(/6% used/);

    // An unknown rendered as an empty bar reads as "nothing used yet", which
    // is the opposite of what it means.
    expect(screen.getAllByRole("meter")).toHaveLength(2);
    expect(screen.getByText("No figure available")).toBeTruthy();
    expect(screen.getByText(/records no limit windows/)).toBeTruthy();
  });

  it("still lists an account with nothing to report", async () => {
    report([claudeUnavailable]);
    render(<UsagePanel projectRoot="/p" />);

    // Omitting it would read as "no such account" rather than "no figure".
    expect(await screen.findByText(/Claude \(subscription\)/)).toBeTruthy();
  });

  it("names an account that no endpoint preset covers", async () => {
    report([
      {
        provider_id: "kimi",
        available: true,
        reason: "",
        observed_at: new Date().toISOString(),
        plan: "",
        limit_id: "",
        windows: [{ label: "5h", window_minutes: 300, used_percent: 8, resets_at: "" }],
        credit_balance: "",
        credits_unlimited: false,
        display_name: "Kimi"
      }
    ]);
    render(<UsagePanel projectRoot="/p" />);

    // Falling back to the raw id would show `kimi`, which is not what the
    // user chose in the sign-in list.
    expect(await screen.findByText("Kimi")).toBeTruthy();
  });

  it("says how old a reading is", async () => {
    report([codex()]);
    render(<UsagePanel projectRoot="/p" />);

    // The figure is whatever the CLI last wrote down, not a live query, so
    // presenting it undated would overstate it.
    expect(await screen.findByText(/3 hours ago/)).toBeTruthy();
  });

  it("reports a percentage above the bar's range rather than trimming it", async () => {
    report([
      codex({
        windows: [{ label: "7d", window_minutes: 10080, used_percent: 105, resets_at: "" }]
      })
    ]);
    render(<UsagePanel projectRoot="/p" />);

    expect(await screen.findByText(/105% used/)).toBeTruthy();
    const meter = screen.getByRole("meter", { name: "7 days" });
    expect((meter.firstElementChild as HTMLElement).style.width).toBe("100%");
  });

  it("falls back to the vendor's own name for a window it does not know", async () => {
    report([
      codex({
        windows: [{ label: "30d", window_minutes: 43200, used_percent: 12, resets_at: "" }]
      })
    ]);
    render(<UsagePanel projectRoot="/p" />);

    // A new window must not render as a blank label the way the model roles
    // once did -- checked as visible text, not only as the accessible name,
    // because the row a user reads is the one that went blank last time.
    expect(await screen.findByText("30d")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "30d" })).toBeTruthy();
  });

  it("omits a reset that was never reported", async () => {
    report([
      codex({
        windows: [{ label: "7d", window_minutes: 10080, used_percent: 12, resets_at: "" }]
      })
    ]);
    render(<UsagePanel projectRoot="/p" />);

    await screen.findByText(/12% used/);
    expect(screen.queryByText(/resets/)).toBeNull();
  });

  it("says no project is open rather than no accounts exist", async () => {
    report([]);
    render(<UsagePanel projectRoot="" />);

    // The figures come through the Agent, which runs per project. "None
    // found" and "could not ask" call for different actions from the user.
    expect(await screen.findByText("No project open")).toBeTruthy();
    expect(screen.queryByText("No subscription accounts.")).toBeNull();
    expect(invoke).not.toHaveBeenCalled();
  });

  it("surfaces a failure to read instead of showing an empty panel", async () => {
    invoke.mockImplementation(() => Promise.reject(new Error("Agent is not running")));
    render(<UsagePanel projectRoot="/p" />);

    await waitFor(() => expect(screen.getByText(/Agent is not running/)).toBeTruthy());
  });
});
