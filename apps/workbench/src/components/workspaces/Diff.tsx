import React from "react";
import { useI18n } from "../../i18n";
import { DIFF_FILE, DIFF_LINES } from "../../fixtures";

const MARKER = { add: "+", delete: "−", context: " " } as const;

export function DiffWorkspace(): React.JSX.Element {
  const { t } = useI18n();

  return (
    <div className="workspace-body">
      <div className="diff-head">
        <span className="mono">{DIFF_FILE.name}</span>
        <span className="mono faint">{DIFF_FILE.stat}</span>
        <div className="card-actions">
          <button type="button" className="secondary-button" disabled>
            {t("diff.discard")}
          </button>
          <button type="button" className="approve-button" disabled>
            {t("diff.approve")}
          </button>
        </div>
      </div>
      <div className="diff-body">
        {DIFF_LINES.map((line, index) => (
          <div key={`${line.kind}-${line.n}-${index}`} className={`diff-line ${line.kind}`}>
            <span className="diff-n">{line.n}</span>
            <span className="diff-marker" aria-hidden="true">
              {MARKER[line.kind]}
            </span>
            <span className="diff-text">{line.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
