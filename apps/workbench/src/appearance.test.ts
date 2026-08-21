import { describe, expect, it } from "vitest";
import {
  ACCENTS,
  APPEARANCE_STORAGE_KEY,
  DEFAULT_APPEARANCE,
  accentColor,
  accentInk,
  loadAppearance,
  resolveTheme,
  saveAppearance
} from "./appearance";

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key) => map.get(key) ?? null,
    key: (index) => [...map.keys()][index] ?? null,
    removeItem: (key) => void map.delete(key),
    setItem: (key, value) => void map.set(key, value)
  };
}

describe("loadAppearance", () => {
  it("returns defaults when nothing is stored", () => {
    expect(loadAppearance(memoryStorage())).toEqual(DEFAULT_APPEARANCE);
  });

  it("round-trips a full preference set", () => {
    const storage = memoryStorage();
    const appearance = {
      theme: "light",
      density: "compact",
      accent: "neon",
      restoreLastProject: false
    } as const;
    saveAppearance(storage, appearance);
    expect(loadAppearance(storage)).toEqual(appearance);
  });

  it("falls back to defaults on malformed JSON", () => {
    const storage = memoryStorage();
    storage.setItem(APPEARANCE_STORAGE_KEY, "{not json");
    expect(loadAppearance(storage)).toEqual(DEFAULT_APPEARANCE);
  });

  it("replaces only the invalid fields of a partial value", () => {
    const storage = memoryStorage();
    storage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({ theme: "light", density: "roomy", accent: "chartreuse" })
    );
    expect(loadAppearance(storage)).toEqual({
      ...DEFAULT_APPEARANCE,
      theme: "light"
    });
  });

  it("ignores a stored non-object", () => {
    const storage = memoryStorage();
    storage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify("dark"));
    expect(loadAppearance(storage)).toEqual(DEFAULT_APPEARANCE);
  });
});

describe("resolveTheme", () => {
  it("honours an explicit choice regardless of the system", () => {
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("follows the system when set to system", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});

describe("accents", () => {
  it("resolves a colour and ink for every shipped accent", () => {
    for (const accent of ACCENTS) {
      expect(accentColor(accent.id)).toMatch(/^#[0-9a-f]{6}$/i);
      expect(accentInk(accent.id)).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});
