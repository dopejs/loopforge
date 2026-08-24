/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The provider list.
 *
 * Two things had no way to happen here at all: removing a provider, and
 * seeing one appear after the wizard saved it. The first had a button that
 * deleted a fixed `openai_compatible` row whatever was on screen; the second
 * was impossible because the wizard was owned a level up, so nothing could ask
 * this list to re-read.
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

const { ProviderSettings } = await import("./ProviderSettings");

function provider(id: string, title: string) {
  return {
    id,
    title,
    family: "anthropic_messages",
    health: "ready",
    ready: true,
    base_url: "https://api.anthropic.com",
    secret_configured: true,
    capabilities: [],
    models: []
  };
}

/** Mutated between reads, so a reload can be observed. */
let inventory: unknown[] = [];

function mockAgent(): void {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_providers") {
      return Promise.resolve({ providers: inventory, roles: [] });
    }
    if (command === "agent_oauth_accounts") return Promise.resolve({ accounts: [] });
    if (command === "agent_provider_settings") {
      return Promise.resolve({ schema_version: "loopforge-settings-v1", provider_id: "" });
    }
    if (command === "agent_forget_provider_settings") {
      return Promise.resolve({ schema_version: "loopforge-settings-v1", provider_id: "" });
    }
    throw new Error(`unexpected command: ${command}`);
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
  inventory = [];
});

describe("ProviderSettings", () => {
  it("removes the provider the user is looking at", async () => {
    inventory = [provider("anthropic", "Anthropic"), provider("zhipu", "Zhipu GLM")];
    mockAgent();
    render(<ProviderSettings projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: /Zhipu GLM/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(
        ([command]) => command === "agent_forget_provider_settings"
      );
      expect(call).toBeTruthy();
      // Not a fixed slot, and not the first one in the list.
      expect((call as [string, Record<string, unknown>])[1].providerId).toBe("zhipu");
    });
  });

  it("re-reads the list once a provider has been removed", async () => {
    inventory = [provider("anthropic", "Anthropic")];
    mockAgent();
    render(<ProviderSettings projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: /Anthropic/ }));
    inventory = [];
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

    // Back on a list that reflects the removal, rather than on a detail page
    // for something that no longer exists.
    expect(await screen.findByText(/no providers/i)).toBeTruthy();
  });

  it("opens the wizard from here, so a save can refresh this list", async () => {
    inventory = [];
    mockAgent();
    render(<ProviderSettings projectRoot="/p" />);

    fireEvent.click(await screen.findByRole("button", { name: "Add provider" }));

    // Owned a level up, the wizard had no way to tell this list anything: a
    // saved provider said "saved" and the list behind it stayed empty.
    expect(await screen.findByRole("dialog")).toBeTruthy();
  });
});
