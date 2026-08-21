import { describe, expect, it } from "vitest";
import {
  LOCALES,
  LOCALE_NAMES,
  LOCALE_STORAGE_KEY,
  detectLocale,
  direction,
  format,
  isLocale,
  loadLocalePreference,
  messages,
  resolveLocale,
  saveLocalePreference
} from "./locale";
import { en } from "./locales/en";

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

describe("catalogues", () => {
  it("ships a complete catalogue for every locale", () => {
    const expected = Object.keys(en).sort();
    for (const locale of LOCALES) {
      expect(Object.keys(messages(locale)).sort(), locale).toEqual(expected);
    }
  });

  it("never leaves a message blank", () => {
    for (const locale of LOCALES) {
      for (const [key, value] of Object.entries(messages(locale))) {
        expect(value.trim(), `${locale}:${key}`).not.toBe("");
      }
    }
  });

  it("preserves interpolation placeholders across translations", () => {
    const placeholders = (value: string): string[] =>
      [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
    for (const locale of LOCALES) {
      const catalogue = messages(locale);
      for (const [key, value] of Object.entries(en)) {
        expect(placeholders(catalogue[key as keyof typeof en]), `${locale}:${key}`).toEqual(
          placeholders(value)
        );
      }
    }
  });

  it("names every locale in its own script", () => {
    for (const locale of LOCALES) {
      expect(LOCALE_NAMES[locale], locale).toBeTruthy();
    }
  });
});

describe("resolveLocale", () => {
  it("maps Chinese by script subtag", () => {
    expect(resolveLocale("zh-Hans")).toBe("zh-Hans");
    expect(resolveLocale("zh-Hant")).toBe("zh-Hant");
    expect(resolveLocale("zh-Hant-TW")).toBe("zh-Hant");
  });

  it("infers Chinese script from the region when no script subtag is present", () => {
    expect(resolveLocale("zh")).toBe("zh-Hans");
    expect(resolveLocale("zh-CN")).toBe("zh-Hans");
    expect(resolveLocale("zh-SG")).toBe("zh-Hans");
    expect(resolveLocale("zh-TW")).toBe("zh-Hant");
    expect(resolveLocale("zh-HK")).toBe("zh-Hant");
    expect(resolveLocale("zh-MO")).toBe("zh-Hant");
  });

  it("matches on the primary language subtag", () => {
    expect(resolveLocale("ja-JP")).toBe("ja");
    expect(resolveLocale("ko-KR")).toBe("ko");
    expect(resolveLocale("es-419")).toBe("es");
    expect(resolveLocale("fr-CA")).toBe("fr");
    expect(resolveLocale("ar-EG")).toBe("ar");
    expect(resolveLocale("en-GB")).toBe("en");
  });

  it("tolerates underscores, casing and whitespace", () => {
    expect(resolveLocale(" ZH_tw ")).toBe("zh-Hant");
    expect(resolveLocale("FR_ca")).toBe("fr");
  });

  it("falls back to English for unshipped or empty tags", () => {
    expect(resolveLocale("de-DE")).toBe("en");
    expect(resolveLocale("")).toBe("en");
    expect(resolveLocale("   ")).toBe("en");
  });
});

describe("detectLocale", () => {
  it("uses the first supported system language", () => {
    expect(detectLocale(["de-DE", "ko-KR", "en-US"])).toBe("ko");
  });

  it("falls back to English when nothing matches", () => {
    expect(detectLocale(["de-DE", "it-IT"])).toBe("en");
    expect(detectLocale([])).toBe("en");
  });
});

describe("direction", () => {
  it("renders Arabic right-to-left and everything else left-to-right", () => {
    expect(direction("ar")).toBe("rtl");
    for (const locale of LOCALES.filter((candidate) => candidate !== "ar")) {
      expect(direction(locale), locale).toBe("ltr");
    }
  });
});

describe("preference storage", () => {
  it("round-trips a chosen locale", () => {
    const storage = memoryStorage();
    saveLocalePreference(storage, "ja");
    expect(storage.getItem(LOCALE_STORAGE_KEY)).toBe("ja");
    expect(loadLocalePreference(storage)).toBe("ja");
  });

  it("clears the preference when following the system", () => {
    const storage = memoryStorage();
    saveLocalePreference(storage, "ja");
    saveLocalePreference(storage, null);
    expect(loadLocalePreference(storage)).toBeNull();
  });

  it("ignores an unshipped stored value rather than crashing", () => {
    const storage = memoryStorage();
    storage.setItem(LOCALE_STORAGE_KEY, "de");
    expect(loadLocalePreference(storage)).toBeNull();
  });
});

describe("format", () => {
  it("substitutes named placeholders", () => {
    expect(format("Revision {value}", { value: 12 })).toBe("Revision 12");
    expect(format("{count} projects", { count: 3 })).toBe("3 projects");
  });

  it("leaves unknown placeholders visible so translation bugs surface", () => {
    expect(format("Revision {value}", { other: 1 })).toBe("Revision {value}");
  });

  it("returns the template untouched when no values are supplied", () => {
    expect(format("Ready")).toBe("Ready");
  });
});

describe("isLocale", () => {
  it("accepts shipped tags only", () => {
    expect(isLocale("zh-Hant")).toBe(true);
    expect(isLocale("de")).toBe(false);
    expect(isLocale(null)).toBe(false);
    expect(isLocale(42)).toBe(false);
  });
});
