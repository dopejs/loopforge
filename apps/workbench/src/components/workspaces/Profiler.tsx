import React from "react";
import { useI18n } from "../../i18n";
import { BarChart, Card, StatCard, type Tone, useKey } from "../primitives";
import { FRAME_BUDGET_MS, FRAME_TIMES, HOTSPOTS, PERF_STATS } from "../../fixtures";

export function ProfilerWorkspace(): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();

  return (
    <div className="workspace-body padded">

      <div className="stat-grid">
        {PERF_STATS.map((stat) => (
          <StatCard
            key={stat.id}
            label={key("perf", stat.id)}
            value={stat.value}
            hint={key("perf", `${stat.id}Hint`)}
            tone={stat.tone as Tone}
          />
        ))}
      </div>

      <Card className="chart-card">
        <div className="board-head">
          <span className="note-label">{t("perf.frameTime")}</span>
          <span className="mono faint">{t("perf.budget", { value: FRAME_BUDGET_MS })}</span>
        </div>
        <BarChart
          values={[...FRAME_TIMES]}
          max={26}
          caption={t("perf.frameTime")}
          toneFor={(value) => (value > FRAME_BUDGET_MS ? "accent" : "info")}
          height={120}
        />
      </Card>

      <Card className="hotspot-table">
        <div className="hotspot-row head">
          <span>{t("perf.hotspot")}</span>
          <span>{t("perf.selfMs")}</span>
          <span>{t("perf.calls")}</span>
          <span>{t("perf.delta")}</span>
        </div>
        {HOTSPOTS.map((hotspot) => (
          <div key={hotspot.name} className="hotspot-row">
            <span className="mono truncate">{hotspot.name}</span>
            <span className="mono dim">{hotspot.ms}</span>
            <span className="mono dim">{hotspot.calls}</span>
            <span className={`mono tone-${hotspot.tone}`}>{hotspot.delta}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}
