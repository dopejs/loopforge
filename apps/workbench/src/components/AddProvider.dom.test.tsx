/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * The provider wizard.
 *
 * The first version of this collapsed the design's three steps into a single
 * endpoint form, so a user had to know a vendor's base URL by heart. These
 * tests pin the structure that was missing: a source is chosen first, choosing
 * one fills in the endpoint, and only then is there a connection to configure.
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

const { AddProvider } = await import("./AddProvider");

function settings(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "loopforge-settings-v1",
    provider_id: "openai_compatible",
    base_url: "",
    model: "",
    display_name: "",
    protocol: "openai_compatible",
    has_api_key: false,
    configured: false,
    ...overrides
  };
}

function mockAgent(overrides: Record<string, unknown> = {}) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_provider_settings") return Promise.resolve(settings(overrides));
    if (command === "agent_providers") return Promise.resolve({ providers: [], roles: [] });
    if (command === "agent_provider_auth" || command === "agent_provider_auth_action") {
      return Promise.resolve({
        schema_version: "loopforge-provider-auth-v1",
        provider_id: "claude_managed",
        status: "login_required",
        checked: true,
        auth_mode: "local_cli_bridge",
        cli_available: true,
        cli_path: "/usr/local/bin/claude",
        account_label: "",
        plan: "",
        login_command: ["claude", "login"],
        logout_command: [],
        last_error: "",
        models: []
      });
    }
    if (command === "agent_save_provider_settings") {
      return Promise.resolve(settings({ ...overrides, configured: true, has_api_key: true }));
    }
    throw new Error(`unexpected command: ${command}`);
  });
}

function open(): void {
  render(
    <AddProvider providers={[]} projectRoot="/p" onClose={() => {}} onSaved={() => {}} />
  );
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("AddProvider", () => {
  it("starts on a list of sources rather than an endpoint form", async () => {
    mockAgent();
    open();

    // The step the first version skipped entirely.
    expect(await screen.findByRole("button", { name: /DeepSeek/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Custom provider/ })).toBeTruthy();
    // Nothing to fill in yet: a source has not been chosen.
    expect(screen.queryByPlaceholderText("https://api.example.com/v1")).toBeNull();
  });

  it("keeps custom reachable when a search matches nothing else", async () => {
    mockAgent();
    open();

    fireEvent.change(await screen.findByPlaceholderText(/Search sources/), {
      target: { value: "zzzz-no-such-vendor" }
    });

    // Custom is the answer when a source is missing, so it must survive the
    // filter that hides everything else.
    expect(screen.getByRole("button", { name: /Custom provider/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /DeepSeek/ })).toBeNull();
    expect(screen.getByText(/No matching source/)).toBeTruthy();
  });

  it("fills in the endpoint from the chosen source", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /DeepSeek/ }));

    // The whole point of the step: not having to know this by heart.
    const baseUrl = screen.getByPlaceholderText("https://api.example.com/v1");
    expect((baseUrl as HTMLInputElement).value).toBe("https://api.deepseek.com/v1");
    expect((screen.getByPlaceholderText("DeepSeek") as HTMLInputElement).value).toBe(
      "DeepSeek"
    );
  });

  it("does not ask a local source for a key", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /Ollama/ }));

    expect(screen.getByText("Local sources need no key.")).toBeTruthy();
    expect(screen.queryByText("API key")).toBeNull();
  });

  it("leaves a custom source's endpoint empty for the user to supply", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /Custom provider/ }));

    expect(
      (screen.getByPlaceholderText("https://api.example.com/v1") as HTMLInputElement).value
    ).toBe("");
  });

  it("carries the source's name and protocol into the save", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /DeepSeek/ }));
    fireEvent.change(screen.getByPlaceholderText("deepseek-chat"), {
      target: { value: "deepseek-chat" }
    });
    fireEvent.change(screen.getByPlaceholderText("Paste the key"), {
      target: { value: "sk-secret" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(
        ([command]) => command === "agent_save_provider_settings"
      );
      expect(call).toBeTruthy();
      const payload = (call as [string, Record<string, unknown>])[1];
      expect(payload.baseUrl).toBe("https://api.deepseek.com/v1");
      // Recorded so the wizard can show what was chosen rather than a bare URL.
      expect(payload.displayName).toBe("DeepSeek");
      expect(payload.protocol).toBe("openai_compatible");
    });
  });

  it("reopens on the connection step for an endpoint already configured", async () => {
    mockAgent({
      base_url: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      display_name: "DeepSeek",
      has_api_key: true,
      configured: true
    });
    open();

    // Revisiting is editing, not starting over, and the stored key is kept
    // rather than demanded again.
    const baseUrl = await screen.findByPlaceholderText("https://api.example.com/v1");
    expect((baseUrl as HTMLInputElement).value).toBe("https://api.deepseek.com/v1");
    expect(screen.getByPlaceholderText(/Leave blank to keep/)).toBeTruthy();
  });

  it("offers subscription accounts as sources", async () => {
    mockAgent();
    open();

    // The design's account tier, which Kura reaches by borrowing a CLI the
    // user has already signed into.
    expect(await screen.findByRole("button", { name: /Claude \(subscription\)/ })).toBeTruthy();
  });

  it("signs an account in rather than asking it for an endpoint", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /Claude \(subscription\)/ }));

    // No endpoint or key: the session was established elsewhere.
    await waitFor(() =>
      expect(screen.queryByPlaceholderText("https://api.example.com/v1")).toBeNull()
    );
    expect(screen.queryByText("API key")).toBeNull();
    expect(await screen.findByRole("button", { name: "Check sign-in" })).toBeTruthy();
  });

  it("shows the command to run rather than pretending to run it", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /Claude \(subscription\)/ }));

    // The login belongs to the user's own account, so the honest instruction
    // is the command, not a button that opens nothing.
    expect(await screen.findByText("claude login")).toBeTruthy();
    expect(screen.getByText(/does not run it for you/)).toBeTruthy();
  });

  it("advances to the models step after saving", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /Custom provider/ }));
    fireEvent.change(screen.getByPlaceholderText("https://api.example.com/v1"), {
      target: { value: "https://api.example.test/v1" }
    });
    fireEvent.change(screen.getByPlaceholderText("model-name"), {
      target: { value: "some-model" }
    });
    fireEvent.change(screen.getByPlaceholderText("Paste the key"), {
      target: { value: "sk-1" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    // And says the endpoint is not live yet, which is why its model list
    // cannot be fetched here.
    expect(await screen.findByText(/Restart the agent/)).toBeTruthy();
  });
});
