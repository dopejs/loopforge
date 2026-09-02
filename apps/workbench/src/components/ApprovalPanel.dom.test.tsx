/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The question the Agent is waiting on.
 *
 * The runtime holds a tool call open for three minutes while a person decides.
 * Until this panel existed the only way to answer was to find the approval id
 * and post to the policy API by hand, so in practice every approval expired and
 * the model reported that nobody had approved it.
 */

const invoke = vi.hoisted(() =>
  vi.fn((_command: string, _args?: unknown): Promise<unknown> =>
    Promise.resolve({ approvals: [] })
  )
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

const { ApprovalPanel } = await import("./ApprovalPanel");

function approval(overrides: Record<string, unknown> = {}) {
  return {
    approval_id: "approval_1",
    action: "tool_call.execute",
    server: "loopforge",
    tool: "loopforge_advance",
    surface: "chat",
    reason: 'run loopforge_advance with {"target_stage":"PROTOTYPING"}',
    requested_by: "agent",
    requested_at: "2026-09-02T05:00:00Z",
    ...overrides
  };
}

/** Answers `agent_approvals` with whatever is currently pending. */
function pending(...items: unknown[]) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_approvals") {
      return Promise.resolve({ schema_version: "loopforge-approval-v1", approvals: items });
    }
    return Promise.resolve({ schema_version: "loopforge-approval-v1", approvals: [] });
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
  invoke.mockImplementation(() => Promise.resolve({ approvals: [] }));
});

describe("ApprovalPanel", () => {
  it("shows nothing when nothing is waiting", async () => {
    pending();
    const { container } = render(<ApprovalPanel projectRoot="/p" enabled />);

    await waitFor(() => expect(invoke).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("shows what is being approved, not only that something is", async () => {
    // "May the agent run `advance`" has no answer without knowing what it
    // would advance to. A panel that showed only the tool name would be a
    // rubber stamp with an audit trail.
    pending(approval());
    render(<ApprovalPanel projectRoot="/p" enabled />);

    expect(await screen.findByText(/target_stage/)).toBeTruthy();
    expect(screen.getByText(/PROTOTYPING/)).toBeTruthy();
  });

  it("sends an approval the waiting call can act on", async () => {
    pending(approval());
    render(<ApprovalPanel projectRoot="/p" enabled />);

    fireEvent.click(await screen.findByRole("button", { name: "Allow" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find((entry) => entry[0] === "agent_resolve_approval");
      expect(call).toBeTruthy();
      const sent = call![1] as Record<string, unknown>;
      expect(sent.approvalId).toBe("approval_1");
      expect(sent.approved).toBe(true);
    });
  });

  it("sends a refusal as a refusal rather than as silence", async () => {
    // A refusal stops the waiting call at once; letting it time out instead
    // would make "no" take three minutes and read as a hang.
    pending(approval());
    render(<ApprovalPanel projectRoot="/p" enabled />);

    fireEvent.click(await screen.findByRole("button", { name: "Deny" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find((entry) => entry[0] === "agent_resolve_approval");
      expect((call![1] as Record<string, unknown>).approved).toBe(false);
    });
  });

  it("keeps asking while a turn is running", async () => {
    // The question appears while a turn is already in flight. Reading once on
    // mount would show nothing and the call would expire unasked.
    pending();
    render(<ApprovalPanel projectRoot="/p" enabled />);

    await waitFor(() => expect(invoke).toHaveBeenCalled());
    const first = invoke.mock.calls.filter((entry) => entry[0] === "agent_approvals").length;

    pending(approval());
    // Longer than one poll interval, or this races the very thing it checks.
    expect(await screen.findByText(/PROTOTYPING/, {}, { timeout: 4000 })).toBeTruthy();
    expect(
      invoke.mock.calls.filter((entry) => entry[0] === "agent_approvals").length
    ).toBeGreaterThan(first);
  });

  it("stops asking once the panel is not enabled", async () => {
    // Polling an Agent that is not running answers nothing and says so
    // repeatedly.
    pending(approval());
    render(<ApprovalPanel projectRoot="/p" enabled={false} />);

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(invoke).not.toHaveBeenCalled();
  });

  it("does not leave the buttons live after an answer", async () => {
    // The next poll removes it, and until then a second click would answer an
    // approval that no longer exists.
    pending(approval());
    render(<ApprovalPanel projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Allow" }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Allow" })).toBeNull()
    );
  });
});
