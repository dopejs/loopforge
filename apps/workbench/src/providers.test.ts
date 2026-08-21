import { describe, expect, it } from "vitest";
import type { ModelRole, ModelRoleName, ProviderInventory } from "./providers";

function role(overrides: Partial<ModelRole> & { role: ModelRoleName }): ModelRole {
  return { provider_id: "", model: "", routed: false, source: "unrouted", ...overrides };
}

/**
 * Mirrors the rendering rule in ProviderSettings: a routed role shows
 * `provider · model`, or just the provider when it uses the provider default.
 */
function describeRoute(route: ModelRole): string {
  return route.model ? `${route.provider_id} · ${route.model}` : route.provider_id;
}

describe("model role display", () => {
  it("names the model when one is pinned", () => {
    expect(
      describeRoute(role({ role: "image", provider_id: "studio", model: "sd3-medium", routed: true }))
    ).toBe("studio · sd3-medium");
  });

  it("shows only the provider when it uses its own default model", () => {
    expect(
      describeRoute(role({ role: "embed", provider_id: "ollama", routed: true }))
    ).toBe("ollama");
  });
});

describe("inventory role states", () => {
  /**
   * These three states must stay distinguishable. Collapsing "no routing
   * support" into "nothing routed" would tell the user to configure something
   * the runtime cannot do.
   */
  it("separates absent routing from an empty routing table", () => {
    const noSupport: ProviderInventory = {
      schema_version: "loopforge-provider-v1",
      providers: []
    };
    const supportedButEmpty: ProviderInventory = {
      schema_version: "loopforge-provider-v1",
      providers: [],
      roles: []
    };
    expect(noSupport.roles).toBeUndefined();
    expect(supportedButEmpty.roles).toEqual([]);
    expect(noSupport.roles === undefined).not.toBe(supportedButEmpty.roles === undefined);
  });

  it("keeps unrouted roles in the list rather than filtering them out", () => {
    const inventory: ProviderInventory = {
      schema_version: "loopforge-provider-v1",
      providers: [],
      roles: [
        role({ role: "primary", provider_id: "anthropic", model: "claude-sonnet", routed: true, source: "config" }),
        role({ role: "video" })
      ]
    };
    // The UI has to show that video generation is unavailable.
    expect(inventory.roles?.map((r) => r.role)).toEqual(["primary", "video"]);
    expect(inventory.roles?.[1].routed).toBe(false);
  });
});
