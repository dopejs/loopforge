import React, { useState } from "react";
import { useI18n } from "../i18n";
import { Card } from "./primitives";
import { errorMessage } from "../daemon";
import { isDesktopRuntime } from "../agent";
import {
  type Evidence,
  chooseCaptureFile,
  evidenceTone,
  registerCapture,
  useEvidence
} from "../evidence";
import type { MessageKey } from "../i18n/locales/en";

const TRUST_KEY: Record<string, MessageKey> = {
  tool_generated: "evidence.trust.tool_generated",
  manually_imported: "evidence.trust.manually_imported",
  human_attested: "evidence.trust.human_attested"
};

/**
 * Registered evidence, and the way to add a screenshot.
 *
 * The control says "register", not "capture", because that is what happens:
 * the core records a file's path and checksum. It does not drive the engine
 * and it does not copy the file, so a screenshot kept outside the project is
 * only referenced and moving it later breaks the link. Both facts are stated
 * rather than left to be discovered.
 *
 * Trust level is shown on every row. A screenshot someone chose is weaker
 * evidence than a run's output, and a decision that cites both needs the
 * difference to be visible.
 */
export function EvidencePanel({
  projectRoot,
  onRegistered
}: {
  projectRoot: string;
  onRegistered?: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const { evidence, reason, loading, reload } = useEvidence(projectRoot, true);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();

  const register = async (): Promise<void> => {
    if (busy || !isDesktopRuntime()) return;
    setFailure(undefined);
    try {
      const path = await chooseCaptureFile();
      if (!path) return; // Cancelled; not a failure.
      setBusy(true);
      await registerCapture(projectRoot, path);
      reload();
      onRegistered?.();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("evidence.registerFailed")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="settings-section">
        <span className="section-title">{t("evidence.section")}</span>
        <button
          type="button"
          className="primary-button small"
          onClick={() => void register()}
          disabled={busy || !isDesktopRuntime()}
        >
          {busy ? t("evidence.registering") : t("evidence.register")}
        </button>
      </div>

      <Card className="suite-list">
        {loading && evidence.length === 0 ? (
          <p className="settings-note">{t("evidence.loading")}</p>
        ) : reason ? (
          <p className="settings-note">{t("evidence.unavailable")}</p>
        ) : evidence.length === 0 ? (
          <p className="settings-note">{t("evidence.none")}</p>
        ) : (
          evidence.map((item: Evidence) => (
            <div key={item.id} className="settings-row">
              <div className="row-label">
                <span>{t(`evidence.type.${item.type}` as MessageKey)}</span>
                <small className="mono">
                  {item.path}
                  {/* An outside file is linked, not held. Saying so here is
                      the only place a user can learn it. */}
                  {item.path_kind === "absolute" && ` · ${t("evidence.linked")}`}
                </small>
              </div>
              <span className="mono faint">
                {t(TRUST_KEY[item.trust_level] ?? "evidence.trust.unknown")}
              </span>
              <span className={`badge ${evidenceTone(item.result) === "ok" ? "ok" : evidenceTone(item.result) === "bad" ? "bad" : ""}`}>
                {t(`evidence.result.${item.result}` as MessageKey)}
              </span>
            </div>
          ))
        )}
      </Card>

      <p className="settings-note">{t("evidence.captureNote")}</p>
      {failure && <p className="settings-note tone-bad">{failure}</p>}
    </>
  );
}
