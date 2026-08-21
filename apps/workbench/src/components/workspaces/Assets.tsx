import React from "react";
import { useI18n } from "../../i18n";
import { ASSETS } from "../../fixtures";

export function AssetsWorkspace(): React.JSX.Element {
  const { t } = useI18n();

  return (
    <div className="workspace-body padded">
      <div className="asset-grid">
        {ASSETS.map((asset) => (
          <article key={asset.name} className="asset-card">
            <div className="asset-thumb">
              <span className="tag">{asset.type}</span>
              {asset.touched && <span className="badge accent">{t("assets.touched")}</span>}
            </div>
            <div className="asset-meta">
              <span className="mono truncate">{asset.name}</span>
              <span className="mono faint">{asset.meta}</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
