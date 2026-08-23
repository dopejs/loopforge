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

/** Signed-in accounts the wizard may offer as a credential. */
let accounts: unknown[] = [];

function mockAgent(overrides: Record<string, unknown> = {}) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_oauth_accounts") return Promise.resolve({ accounts });
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
    if (command === "agent_probe_provider") {
      return Promise.resolve({
        schema_version: "loopforge-provider-probe-v1",
        reachable: true,
        models: ["deepseek-chat", "deepseek-reasoner"]
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
  accounts = [];
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

  it("shows a preset's endpoint rather than asking for it", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /DeepSeek/ }));

    // Choosing a preset is how a user avoids having to know this. Presenting
    // it as a field to fill in asks for the very thing they just chose.
    expect(screen.queryByPlaceholderText("https://api.example.com/v1")).toBeNull();
    expect(screen.getByText("https://api.deepseek.com/v1")).toBeTruthy();
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
    fireEvent.change(screen.getByPlaceholderText("Paste the key"), {
      target: { value: "sk-secret" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(await screen.findByPlaceholderText("deepseek-chat"), {
      target: { value: "deepseek-chat" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(
        ([command]) => command === "agent_save_provider_settings"
      );
      expect(call).toBeTruthy();
      const payload = (call as [string, Record<string, unknown>])[1];
      expect(payload.baseUrl).toBe("https://api.deepseek.com/v1");
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
    expect(await screen.findByPlaceholderText(/Leave blank to keep/)).toBeTruthy();
    expect(screen.getByText("https://api.deepseek.com/v1")).toBeTruthy();
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

  it("asks the endpoint for its catalogue on the way to the model step", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /DeepSeek/ }));
    fireEvent.change(screen.getByPlaceholderText("Paste the key"), {
      target: { value: "sk-secret" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    // The step is named for the model, so the list has to be there when the
    // user arrives -- not something they press a button for.
    expect(await screen.findByText(/Choose the model/)).toBeTruthy();
    const call = invoke.mock.calls.find(([command]) => command === "agent_probe_provider");
    expect((call as [string, Record<string, unknown>])[1].apiKey).toBe("sk-secret");
  });


  it("stops on a rejected key instead of moving on", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "agent_provider_settings") return Promise.resolve(settings());
      if (command === "agent_providers") return Promise.resolve({ providers: [], roles: [] });
      if (command === "agent_oauth_accounts") return Promise.resolve({ accounts: [] });
      if (command === "agent_probe_provider") {
        return Promise.resolve({
          schema_version: "loopforge-provider-probe-v1",
          reachable: false,
          status: 401,
          models: []
        });
      }
      throw new Error(`unexpected command: ${command}`);
    });
    open();

    fireEvent.click(await screen.findByRole("button", { name: /DeepSeek/ }));
    fireEvent.change(screen.getByPlaceholderText("Paste the key"), {
      target: { value: "sk-wrong" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    // Advancing would hide the one thing the user has to fix.
    expect(await screen.findByText("The endpoint rejected this key.")).toBeTruthy();
    expect(screen.queryByText(/Choose the model/)).toBeNull();
  });


  it("offers no account for a vendor that has none", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /DeepSeek/ }));

    // DeepSeek has no subscription sign-in. A disabled toggle here told the
    // user an account might exist for an endpoint that has none.
    expect(screen.queryByRole("button", { name: "Use a signed-in account" })).toBeNull();
    expect(screen.getByPlaceholderText("Paste the key")).toBeTruthy();
  });


  it("takes the credential from the vendor's own account", async () => {
    accounts = [
      { id: "xai", name: "xAI", flow: "device_code", signed_in: true,
        account_label: "", plan: "", expires_at: "", grant_deadline: "", configured: true }
    ];
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /^xAI/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Use a signed-in account" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(await screen.findByPlaceholderText("grok-4"), {
      target: { value: "grok-4" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      const call = invoke.mock.calls.find(
        ([command]) => command === "agent_save_provider_settings"
      );
      expect((call as [string, Record<string, unknown>])[1].oauthProviderId).toBe("xai");
    });
  });


  it("signs the account in from here rather than sending the user away", async () => {
    accounts = [
      { id: "xai", name: "xAI", flow: "device_code", signed_in: false,
        account_label: "", plan: "", expires_at: "", grant_deadline: "", configured: true }
    ];
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /^xAI/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Use a signed-in account" }));

    // The account is a credential for this endpoint, so it is established
    // here. Sending the user to the usage panel and back inverted that.
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
    expect(screen.queryByPlaceholderText("Paste the key")).toBeNull();
  });


  it("reaches the model step without having asked for a model first", async () => {
    mockAgent();
    open();

    fireEvent.click(await screen.findByRole("button", { name: /Custom provider/ }));
    fireEvent.change(screen.getByPlaceholderText("https://api.example.com/v1"), {
      target: { value: "https://api.example.test/v1" }
    });
    fireEvent.change(screen.getByPlaceholderText("Paste the key"), {
      target: { value: "sk-1" }
    });

    // Step two asked only for the credential; naming a model belongs to the
    // step named for it.
    expect(screen.queryByPlaceholderText("model-name")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByPlaceholderText("model-name")).toBeTruthy();
  });

});
