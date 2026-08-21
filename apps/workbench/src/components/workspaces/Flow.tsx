import React from "react";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/locales/en";

/**
 * The pipeline laid out as the design draws it: trigger → plan → edit across
 * the top row, test → review beneath. `arrow` records the edges leaving each
 * node so the connectors only ever point at a real successor.
 */
const NODES = [
  { id: "trigger", column: 1, row: 1, tone: "", arrow: "right", steps: false },
  { id: "plan", column: 2, row: 1, tone: "accent", arrow: "right", steps: true },
  { id: "edit", column: 3, row: 1, tone: "", arrow: "down", steps: false },
  { id: "test", column: 2, row: 2, tone: "", arrow: "right", steps: false },
  { id: "review", column: 3, row: 2, tone: "ok", arrow: "", steps: false }
] as const;

export function FlowWorkspace(): React.JSX.Element {
  const { t } = useI18n();

  return (
    <div className="workspace-body">
      <div className="flow-surface">
        <div className="flow-grid">
          {NODES.map((node) => (
            <section
              key={node.id}
              className={`flow-node${node.tone === "accent" ? " accent" : ""}`}
              style={{ gridColumn: node.column, gridRow: node.row }}
              data-arrow={node.arrow || undefined}
            >
              <div className="node-head">
                <span className={`note-label ${node.tone}`.trim()}>
                  {t(`flow.${node.id}` as MessageKey)}
                </span>
                {node.steps && (
                  <span className="mono faint node-steps">{t("flow.steps", { count: 4 })}</span>
                )}
              </div>
              <strong>{t(`flow.${node.id}Title` as MessageKey)}</strong>
              {node.id !== "trigger" && (
                <p className="dim">{t(`flow.${node.id}Body` as MessageKey)}</p>
              )}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
