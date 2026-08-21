import React, { useState } from "react";
import { useI18n } from "../../i18n";
import { BarChart, Card, useKey } from "../primitives";
import {
  CANVAS_ASSETS,
  CANVAS_FEEDBACK,
  CANVAS_NOTE,
  CANVAS_TARGETS,
  CANVAS_TOOLS,
  type CanvasTool,
  DEATHS_PER_ATTEMPT
} from "../../fixtures";

const TOOL_GLYPHS: Record<CanvasTool, string> = {
  select: "⌖",
  hand: "✥",
  note: "▤",
  frame: "▢",
  link: "↝",
  image: "◧"
};

export function CanvasWorkspace(): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();
  const [tool, setTool] = useState<CanvasTool>("select");

  return (
    <div className="workspace-body">
      <div className="canvas-surface">
        <div className="canvas-scroll">
          <Card className="canvas-board">
            <div className="board-head">
              <strong>Boss Phase 2 · combat tuning</strong>
              <span className="mono faint">{t("canvas.objects", { count: 4 })}</span>
            </div>
            <div className="board-grid">
              {CANVAS_ASSETS.map((asset) => (
                <div key={asset.name} className="asset-slot">
                  <span className="mono">{asset.name}</span>
                  <span className="mono faint">{asset.meta}</span>
                </div>
              ))}
              <div className="board-note">
                <span className="note-label">{t("canvas.agentNote")}</span>
                <p>{CANVAS_NOTE}</p>
              </div>
            </div>
          </Card>

          <Card className="canvas-feedback">
            <span className="note-label accent">{t("canvas.playtestFeedback")}</span>
            <p className="quote">“{CANVAS_FEEDBACK.quote}”</p>
            <span className="faint">— {CANVAS_FEEDBACK.author}</span>
          </Card>

          <Card className="canvas-targets">
            <span className="note-label">{t("canvas.targetRange")}</span>
            <dl>
              {CANVAS_TARGETS.map((target) => (
                <div key={target.id} className="target-row">
                  <dt>{key("canvas", target.id === "deaths" ? "deathsPerClear" : target.id === "clear" ? "clearRate" : "minFps")}</dt>
                  <dd className={target.ok ? "tone-ok" : "tone-bad"}>{target.value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="canvas-chart">
            <div className="board-head">
              <span className="note-label">{t("canvas.deathsChart")}</span>
              <span className="mono tone-ok">−38%</span>
            </div>
            <BarChart
              values={[...DEATHS_PER_ATTEMPT]}
              max={6}
              caption={t("canvas.deathsChart")}
              toneFor={(_value, index) => (index > 14 ? "ok" : "faint")}
            />
          </Card>

          <Card className="canvas-working">
            <div className="working-head">
              <span className="spinner" aria-hidden="true" />
              <strong>{t("canvas.agentWorking")}</strong>
            </div>
            <p className="dim">{t("canvas.agentWorkingBody")}</p>
            <div className="working-slots">
              <span />
              <span />
              <span className="pending" />
            </div>
          </Card>
        </div>

        <div className="canvas-toolbar" role="toolbar" aria-label={t("mode.canvas")}>
          {CANVAS_TOOLS.map((candidate) => (
            <button
              key={candidate}
              type="button"
              className={candidate === tool ? "canvas-tool active" : "canvas-tool"}
              aria-pressed={candidate === tool}
              aria-label={key("tool", candidate)}
              title={key("tool", candidate)}
              onClick={() => setTool(candidate)}
            >
              {TOOL_GLYPHS[candidate]}
            </button>
          ))}
          <span className="toolbar-divider" />
          <span className="mono dim">72%</span>
        </div>
      </div>
    </div>
  );
}
