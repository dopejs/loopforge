import React from "react";
import { Icon } from "../icons";
import { WORKSPACE_MODES, type Mode, modeLabelKey } from "../modes";
import { useI18n } from "../i18n";
import badge from "../assets/loopforge-badge-square.svg";
import { startWindowDrag } from "../window";

export function IconRail({
  mode,
  onSelect
}: {
  mode: Mode;
  onSelect: (mode: Mode) => void;
}): React.JSX.Element {
  const { t } = useI18n();

  const button = (target: Mode): React.JSX.Element => {
    const label = t(modeLabelKey(target));
    return (
      <button
        key={target}
        type="button"
        className={target === mode ? "rail-button active" : "rail-button"}
        onClick={() => onSelect(target)}
        aria-current={target === mode ? "page" : undefined}
        aria-label={label}
        title={label}
      >
        <Icon name={target} />
      </button>
    );
  };

  return (
    <nav className="icon-rail" aria-label={t("app.workbench")} onMouseDown={startWindowDrag}>
      {/* Sits below the overlay title bar's traffic lights; see .icon-rail padding. */}
      <img className="rail-badge" src={badge} alt={t("app.name")} draggable={false} />
      <div className="rail-group">{WORKSPACE_MODES.map(button)}</div>
      <div className="rail-spacer" />
      <div className="rail-divider" />
      {button("settings")}
    </nav>
  );
}
