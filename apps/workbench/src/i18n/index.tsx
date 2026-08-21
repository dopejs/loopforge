import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { MessageKey } from "./locales/en";
import {
  type Direction,
  type Locale,
  type LocalePreference,
  detectLocale,
  direction,
  format,
  loadLocalePreference,
  messages,
  saveLocalePreference
} from "./locale";

export type Translate = (
  key: MessageKey,
  values?: Readonly<Record<string, string | number>>
) => string;

type I18nValue = {
  /** The locale actually in use, after resolving a `null` (system) preference. */
  locale: Locale;
  /** What the user chose; `null` means "follow the system". */
  preference: LocalePreference;
  direction: Direction;
  t: Translate;
  setPreference: (preference: LocalePreference) => void;
};

const I18nContext = createContext<I18nValue | null>(null);

function systemLocale(): Locale {
  if (typeof navigator === "undefined") return "en";
  const tags = navigator.languages?.length ? navigator.languages : [navigator.language];
  return detectLocale(tags.filter((tag): tag is string => typeof tag === "string"));
}

export function I18nProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [preference, setPreferenceState] = useState<LocalePreference>(() =>
    loadLocalePreference(localStorage)
  );
  const [system, setSystem] = useState<Locale>(systemLocale);

  // Following the system means following it for the whole session, not only at
  // launch: macOS can change the preferred language while the app is running.
  useEffect(() => {
    if (preference !== null || typeof window === "undefined") return;
    const onLanguageChange = (): void => setSystem(systemLocale());
    window.addEventListener("languagechange", onLanguageChange);
    return () => window.removeEventListener("languagechange", onLanguageChange);
  }, [preference]);

  const locale = preference ?? system;
  const dir = direction(locale);
  const catalogue = messages(locale);

  const setPreference = useCallback((next: LocalePreference): void => {
    saveLocalePreference(localStorage, next);
    setPreferenceState(next);
    if (next === null) setSystem(systemLocale());
  }, []);

  const t = useCallback<Translate>(
    (key, values) => format(catalogue[key], values),
    [catalogue]
  );

  // Screen readers and the browser's own bidi algorithm both key off these.
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
  }, [dir, locale]);

  const value = useMemo<I18nValue>(
    () => ({ locale, preference, direction: dir, t, setPreference }),
    [dir, locale, preference, setPreference, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside an I18nProvider");
  return value;
}

export type { Locale, LocalePreference, Direction, MessageKey };
