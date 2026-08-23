/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * Signing subscription accounts in.
 *
 * The two flows put different things in front of the user -- a redirect to
 * follow, or a short code to type -- and showing the wrong one leaves them
 * waiting on a page that will never redirect. The other thing worth pinning is
 * the order: the Agent binds the fixed redirect port when the sign-in starts,
 * so a browser opened before that finds nothing listening.
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

const { AccountsPanel } = await import("./AccountsPanel");

function account(overrides: Record<string, unknown> = {}) {
  return {
    id: "anthropic",
    name: "Claude",
    flow: "callback",
    signed_in: false,
    account_label: "",
    plan: "",
    expires_at: "",
    grant_deadline: "",
    ...overrides
  };
}

function wire(options: {
  accounts?: unknown[];
  begin?: unknown;
  complete?: unknown;
  order?: string[];
}) {
  const order = options.order ?? [];
  invoke.mockImplementation((command: string) => {
    order.push(command);
    if (command === "agent_oauth_accounts") {
      return Promise.resolve({ accounts: options.accounts ?? [account()] });
    }
    if (command === "agent_oauth_begin") {
      return Promise.resolve(
        options.begin ?? {
          provider_id: "anthropic",
          flow: "callback",
          url: "https://claude.ai/oauth/authorize?x=1",
          user_code: ""
        }
      );
    }
    if (command === "agent_oauth_complete") {
      // A never-settling promise where a test is watching the waiting state:
      // this call *is* the wait, and resolving it at once skips the very UI
      // the user spends the sign-in looking at.
      if (options.complete === "pending") return new Promise(() => {});
      return Promise.resolve(
        options.complete ?? { accounts: [account({ signed_in: true, plan: "max" })] }
      );
    }
    if (command === "agent_oauth_sign_out") {
      return Promise.resolve({ accounts: [account({ signed_in: false })] });
    }
    if (command === "open_external") return Promise.resolve();
    throw new Error(`unexpected command: ${command}`);
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("AccountsPanel", () => {
  it("offers a sign-in for an account that has none", async () => {
    wire({});
    render(<AccountsPanel projectRoot="/p" />);

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeTruthy();
  });

  it("opens the browser only after the sign-in has been started", async () => {
    const order: string[] = [];
    wire({ order });
    render(<AccountsPanel projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(order).toContain("open_external"));
    // The Agent binds the provider's fixed redirect port in `begin`. A browser
    // sent first would arrive at a port with nothing on it.
    expect(order.indexOf("agent_oauth_begin")).toBeLessThan(order.indexOf("open_external"));
  });

  it("shows the code to type for an account that has no redirect", async () => {
    wire({
      accounts: [account({ id: "github_copilot", name: "GitHub Copilot", flow: "device_code" })],
      begin: {
        provider_id: "github_copilot",
        flow: "device_code",
        url: "https://github.com/login/device",
        user_code: "WXYZ-1234"
      },
      complete: "pending"
    });
    render(<AccountsPanel projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));

    // Without this the user waits for a redirect that is never coming.
    expect(await screen.findByText("WXYZ-1234")).toBeTruthy();
    expect(screen.getByText(/Enter this code/)).toBeTruthy();
  });

  it("does not show a code for a redirect sign-in", async () => {
    wire({ complete: "pending" });
    render(<AccountsPanel projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/Waiting for you to finish/)).toBeTruthy();
    expect(screen.queryByText(/Enter this code/)).toBeNull();
  });

  it("reflects the account as signed in once it completes", async () => {
    wire({});
    render(<AccountsPanel projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(screen.getByText("max")).toBeTruthy();
  });

  it("reports a refused sign-in instead of appearing to succeed", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "agent_oauth_accounts") return Promise.resolve({ accounts: [account()] });
      if (command === "agent_oauth_begin") {
        return Promise.reject(new Error("Cannot listen on port 54545"));
      }
      throw new Error(`unexpected command: ${command}`);
    });
    render(<AccountsPanel projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/Cannot listen on port 54545/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
  });

  it("says that signing out is local", async () => {
    wire({ accounts: [account({ signed_in: true })] });
    render(<AccountsPanel projectRoot="/p" />);

    // Otherwise it reads as ending the session at the vendor, which it is not.
    expect(await screen.findByText(/does not end the session at the vendor/)).toBeTruthy();
  });

  it("warns before a grant has to be re-established", async () => {
    const soon = new Date(Date.now() + 3 * 86_400_000).toISOString();
    wire({ accounts: [account({ signed_in: true, grant_deadline: soon })] });
    render(<AccountsPanel projectRoot="/p" />);

    // This one does not renew itself, so it strands a session if unnoticed.
    expect(await screen.findByText(/Sign in again within 3 days/)).toBeTruthy();
  });

  it("stays quiet about a deadline that is far off", async () => {
    const later = new Date(Date.now() + 25 * 86_400_000).toISOString();
    wire({ accounts: [account({ signed_in: true, grant_deadline: later })] });
    render(<AccountsPanel projectRoot="/p" />);

    await screen.findByRole("button", { name: "Sign out" });
    expect(screen.queryByText(/Sign in again/)).toBeNull();
  });
});
