import React from "react";
import { useI18n } from "../../i18n";
import { BarChart, Card, StatCard, type Tone, useKey } from "../primitives";
import {
  PLAYTEST_FPS,
  PLAYTEST_SUMMARY,
  TEST_FAILURE,
  TEST_STATS,
  TEST_SUITES
} from "../../fixtures";

export function TestWorkspace(): React.JSX.Element {
  const { t } = useI18n();
  const key = useKey();

  return (
    <div className="workspace-body padded">

      <div className="stat-grid">
        {TEST_STATS.map((stat) => (
          <StatCard
            key={stat.id}
            label={key("test", stat.id)}
            value={stat.value}
            hint={key("test", `${stat.id}Hint`)}
            tone={stat.tone as Tone}
          />
        ))}
      </div>

      <Card className="suite-list">
        {TEST_SUITES.map((suite) => (
          <div key={suite.name} className="suite-row">
            <span className={suite.failed ? "state-dot bad" : "state-dot ok"} aria-hidden="true" />
            <span className="suite-name mono">{suite.name}</span>
            <span className="suite-meter" aria-hidden="true">
              <span className="meter-pass" style={{ width: `${suite.pass}%` }} />
              <span className="meter-fail" style={{ width: `${100 - suite.pass}%` }} />
            </span>
            <span className="mono dim suite-count">{suite.count}</span>
            <span className="mono faint suite-time">{suite.time}</span>
          </div>
        ))}
      </Card>

      <div className="split-grid">
        <Card className="failure-card">
          <div className="board-head">
            <span className="badge bad">{t("test.failedBadge")}</span>
            <span className="mono truncate">{TEST_FAILURE.suite}</span>
          </div>
          <pre className="failure-body">
            {TEST_FAILURE.lines.join("\n")}
            {"\n"}
            <span className="faint">{TEST_FAILURE.at}</span>
          </pre>
          <div className="card-actions">
            <button type="button" className="primary-button" disabled>
              {t("test.fixWithAgent")}
            </button>
            <button type="button" className="secondary-button" disabled>
              {t("test.rerun")}
            </button>
          </div>
        </Card>

        <Card className="sim-card">
          <div className="board-head">
            <span className="note-label">{t("test.playtestSim")}</span>
            <span className="mono tone-ok">{t("test.avgFps", { value: PLAYTEST_SUMMARY.avg })}</span>
          </div>
          <BarChart
            values={[...PLAYTEST_FPS]}
            max={62}
            caption={t("test.playtestSim")}
            toneFor={(value) => (value < 55 ? "bad" : "ok")}
            height={76}
          />
          <div className="sim-summary mono dim">
            <span>{t("test.minFpsValue", { value: PLAYTEST_SUMMARY.min })}</span>
            <span>{t("test.deathsValue", { value: PLAYTEST_SUMMARY.deaths })}</span>
            <span>{t("test.clearValue", { value: PLAYTEST_SUMMARY.clear })}</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
