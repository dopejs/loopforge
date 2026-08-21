import React from "react";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/locales/en";

export type Tone = "ok" | "bad" | "text" | "faint" | "accent" | "info";

/**
 * Marks a surface as rendering placeholder data. Every preview workspace shows
 * one, so nothing on screen can be mistaken for real project data.
 */
export function PreviewBanner(): React.JSX.Element {
  const { t } = useI18n();
  return (
    <div className="preview-banner" role="note">
      <span className="preview-badge">{t("preview.badge")}</span>
      <span className="preview-text">{t("preview.note")}</span>
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "text"
}: {
  label: string;
  value: string;
  hint: string;
  tone?: Tone;
}): React.JSX.Element {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className={`stat-value tone-${tone}`}>{value}</strong>
      <span className="stat-hint">{hint}</span>
    </div>
  );
}

/**
 * Simple column chart. Bars are decorative; `caption` names the series for
 * assistive technology, since the numbers are summarised in adjacent text.
 */
export function BarChart({
  values,
  max,
  caption,
  toneFor,
  height = 74
}: {
  values: readonly number[];
  max: number;
  caption: string;
  toneFor: (value: number, index: number) => Tone;
  height?: number;
}): React.JSX.Element {
  return (
    <div className="bar-chart" style={{ height }} role="img" aria-label={caption}>
      {values.map((value, index) => (
        <span
          key={index}
          className={`bar tone-${toneFor(value, index)}`}
          style={{ height: `${Math.max(2, Math.round((value / max) * 100))}%` }}
        />
      ))}
    </div>
  );
}

export function SectionLabel({
  children,
  trailing
}: {
  children: React.ReactNode;
  trailing?: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="section-head">
      <span className="section-title">{children}</span>
      {trailing !== undefined && <span className="section-trailing">{trailing}</span>}
    </div>
  );
}

export function Card({
  children,
  className = ""
}: {
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return <div className={`panel-card ${className}`.trim()}>{children}</div>;
}

/** Renders a `role.*` / `provider.*` style key without widening MessageKey. */
export function useKey(): (prefix: string, suffix: string) => string {
  const { t } = useI18n();
  return (prefix, suffix) => t(`${prefix}.${suffix}` as MessageKey);
}
