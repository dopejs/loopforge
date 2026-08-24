import { describe, expect, it } from "vitest";
import { SOURCES, needsApiKey } from "./sources";

/**
 * The preset list.
 *
 * A source's id is the id the provider is stored and dispatched under, so
 * these are not cosmetic. Two presets sharing one meant two vendors sharing
 * one provider slot -- adding the second replaced the first, silently, which
 * is the same shape as the single `openai_compatible` slot everything used to
 * land in.
 */
describe("SOURCES", () => {
  it("gives every source its own id", () => {
    const seen = new Map<string, string[]>();
    for (const source of SOURCES) {
      seen.set(source.id, [...(seen.get(source.id) ?? []), source.name]);
    }
    const duplicated = [...seen.entries()].filter(([, names]) => names.length > 1);
    expect(duplicated).toEqual([]);
  });

  it("separates a vendor's key path from its subscription", () => {
    // Two presets may share an endpoint -- Moonshot's key path and Kimi's
    // subscription are the same URL -- but then exactly one of them carries
    // the account, or picking either would configure the same thing.
    const byUrl = new Map<string, typeof SOURCES[number][]>();
    for (const source of SOURCES) {
      if (!source.baseUrl) continue;
      const key = source.baseUrl.replace(/\/+$/, "").toLowerCase();
      byUrl.set(key, [...(byUrl.get(key) ?? []), source]);
    }
    for (const [url, shared] of byUrl) {
      if (shared.length === 1) continue;
      const withAccount = shared.filter((source) => source.oauthProviderId);
      expect(`${url}: ${withAccount.length}`).toBe(`${url}: 1`);
    }
  });

  it("names the wire a vendor actually speaks", () => {
    // Anthropic does not serve the OpenAI shape, and it does not serve it at
    // a `/v1` suffix either. Listed that way, choosing the preset and pasting
    // a key configured a provider that could not answer a single request.
    const anthropic = SOURCES.find((source) => source.id === "anthropic");
    expect(anthropic?.protocol).toBe("anthropic_messages");
    expect(anthropic?.baseUrl).toBe("https://api.anthropic.com");

    const codex = SOURCES.find((source) => source.id === "codex");
    expect(codex?.protocol).toBe("openai_responses");
  });

  it("asks for a credential everywhere except a local endpoint", () => {
    for (const source of SOURCES) {
      expect(needsApiKey(source)).toBe(source.kind !== "local");
    }
  });
});
