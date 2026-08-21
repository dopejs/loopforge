import type { Messages } from "./locales/en";
import { en } from "./locales/en";
import { zhHans } from "./locales/zh-Hans";
import { zhHant } from "./locales/zh-Hant";
import { ar } from "./locales/ar";
import { es } from "./locales/es";
import { fr } from "./locales/fr";
import { ja } from "./locales/ja";
import { ko } from "./locales/ko";

export const LOCALE_STORAGE_KEY = "loopforge.locale";

/** BCP 47 tags for every shipped locale. Order drives the settings list. */
export const LOCALES = [
  "en",
  "zh-Hans",
  "zh-Hant",
  "ja",
  "ko",
  "es",
  "fr",
  "ar"
] as const;

export type Locale = (typeof LOCALES)[number];

/** `null` means "follow the operating system", which is the default. */
export type LocalePreference = Locale | null;

export type Direction = "ltr" | "rtl";

const CATALOGUES: Record<Locale, Messages> = {
  en,
  "zh-Hans": zhHans,
  "zh-Hant": zhHant,
  ja,
  ko,
  es,
  fr,
  ar
};

/**
 * Endonyms: a language list is only useful to someone who cannot read the
 * current interface language, so each locale names itself in its own script.
 */
export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  "zh-Hans": "简体中文",
  "zh-Hant": "繁體中文",
  ja: "日本語",
  ko: "한국어",
  es: "Español",
  fr: "Français",
  ar: "العربية"
};

const RTL_LOCALES: ReadonlySet<Locale> = new Set<Locale>(["ar"]);

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

export function direction(locale: Locale): Direction {
  return RTL_LOCALES.has(locale) ? "rtl" : "ltr";
}

export function messages(locale: Locale): Messages {
  return CATALOGUES[locale];
}

/**
 * Resolves a browser/OS language tag to a shipped locale.
 *
 * Chinese is the awkward case: `zh-TW`, `zh-HK` and `zh-MO` are Traditional
 * while bare `zh` and `zh-CN` are Simplified, so script is inferred from the
 * region when no explicit `Hans`/`Hant` subtag is present. Everything else
 * matches on the primary language subtag, then falls back to English.
 */
export function resolveLocale(tag: string): Locale {
  const normalized = tag.trim().toLowerCase();
  if (!normalized) return "en";
  const [language, ...rest] = normalized.split(/[-_]/);

  if (language === "zh") {
    if (rest.includes("hant")) return "zh-Hant";
    if (rest.includes("hans")) return "zh-Hans";
    return rest.some((part) => ["tw", "hk", "mo"].includes(part)) ? "zh-Hant" : "zh-Hans";
  }

  const direct = LOCALES.find((locale) => locale.toLowerCase() === normalized);
  if (direct) return direct;

  const byLanguage = LOCALES.find((locale) => locale.toLowerCase() === language);
  return byLanguage ?? "en";
}

/** Picks the first system language tag that maps to a shipped locale. */
export function detectLocale(tags: readonly string[]): Locale {
  for (const tag of tags) {
    const [language] = tag.trim().toLowerCase().split(/[-_]/);
    if (!language) continue;
    if (language === "zh" || LOCALES.some((locale) => locale.toLowerCase().split("-")[0] === language)) {
      return resolveLocale(tag);
    }
  }
  return "en";
}

export function loadLocalePreference(storage: Storage): LocalePreference {
  const saved = storage.getItem(LOCALE_STORAGE_KEY);
  return isLocale(saved) ? saved : null;
}

export function saveLocalePreference(storage: Storage, preference: LocalePreference): void {
  if (preference === null) {
    storage.removeItem(LOCALE_STORAGE_KEY);
    return;
  }
  storage.setItem(LOCALE_STORAGE_KEY, preference);
}

/**
 * Substitutes `{name}` placeholders. Unknown placeholders are left verbatim so
 * a translation bug shows up in the UI instead of silently rendering nothing.
 */
export function format(template: string, values?: Readonly<Record<string, string | number>>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match
  );
}
