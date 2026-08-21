import React, { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import type { AgentPhase, AgentState, TranscriptEntry } from "../agent";
import { AGENT_PLAN, AGENT_TOOL_CALLS, COMPOSER_CHIPS, PREVIEW_PROJECT } from "../fixtures";

export function Composer({
  disabled,
  busy,
  inputRef,
  onSend
}: {
  disabled: boolean;
  busy: boolean;
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
  onSend: (query: string) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");

  const submit = (): void => {
    const trimmed = draft.trim();
    if (!trimmed || disabled || busy) return;
    setDraft("");
    onSend(trimmed);
  };

  return (
    <div className="composer">
      <div className="composer-chips">
        {COMPOSER_CHIPS.map((chip) => (
          <button
            key={chip}
            type="button"
            className="composer-chip"
            disabled={disabled}
            onClick={() => setDraft((current) => (current ? `${current} ${chip} ` : `${chip} `))}
          >
            {chip}
          </button>
        ))}
      </div>
      <textarea
        ref={inputRef}
        value={draft}
        rows={2}
        disabled={disabled}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends; Shift+Enter and the platform modifiers insert a newline.
          if (event.key === "Enter" && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={t("agent.composerPlaceholder")}
        aria-label={t("agent.composerPlaceholder")}
      />
      <button
        type="button"
        className="primary-button send"
        onClick={submit}
        disabled={disabled || busy || !draft.trim()}
      >
        {busy ? t("agent.sending") : t("agent.send")}
      </button>
    </div>
  );
}

export function Transcript({
  transcript,
  busy,
  variant
}: {
  transcript: readonly TranscriptEntry[];
  busy: boolean;
  variant: "panel" | "page";
}): React.JSX.Element {
  const { t } = useI18n();
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [busy, transcript]);

  if (transcript.length === 0 && !busy) {
    return (
      <div className={`transcript ${variant} empty`}>
        <div className="transcript-empty">
          <strong>{t("agent.emptyTitle")}</strong>
          <span>{t("agent.emptyBody")}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`transcript ${variant}`} aria-live="polite">
      {transcript.map((entry) => (
        <article
          key={entry.id}
          className={`message ${entry.author}${entry.failed ? " failed" : ""}`}
        >
          <span className="message-author">
            {entry.author === "user" ? t("agent.you") : t("agent.title")}
          </span>
          <p className="message-text">{entry.text}</p>
        </article>
      ))}
      {busy && (
        <p className="message-pending">
          <span className="spinner" aria-hidden="true" />
          {t("agent.status.working")}
        </p>
      )}
      <div ref={end} />
    </div>
  );
}

export function AgentPanel({
  phase,
  state,
  transcript,
  busy,
  composerRef,
  onSend
}: {
  phase: AgentPhase;
  state: AgentState;
  transcript: readonly TranscriptEntry[];
  busy: boolean;
  composerRef: React.RefObject<HTMLTextAreaElement | null>;
  onSend: (query: string) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const nextActions = state.project?.next_actions ?? [];
  const realPlan = nextActions.length > 0;
  const steps = realPlan
    ? nextActions.map((title) => ({ title, meta: "", state: "done" as const }))
    : AGENT_PLAN.map((step) => ({ ...step }));

  const status = {
    unsupported: t("agent.status.unsupported"),
    "no-project": t("agent.status.noProject"),
    starting: t("agent.status.starting"),
    ready: busy ? t("agent.status.working") : t("agent.status.ready"),
    offline: t("agent.status.offline")
  }[phase];

  return (
    <aside className="agent-panel" aria-label={t("agent.title")}>
      <header className="panel-header">
        <div className="section-head">
          <span className="section-title">{t("agent.title")}</span>
          <span className="mono faint">{t("agent.runId", { id: PREVIEW_PROJECT.runId })}</span>
        </div>
        <p className={`agent-state ${phase}`}>
          <span className="state-dot" aria-hidden="true" />
          {status}
        </p>
      </header>

      {/*
        `loopforge-agent-status-v1` carries no plan steps, so the timeline is
        driven by `next_actions` when the Agent reports them and falls back to
        preview steps otherwise — flagged as preview in that case.
      */}
      <section className="panel-plan">
        <div className="section-head">
          <span className="section-title">{t("agent.plan")}</span>
          {!realPlan && (
            <span className="preview-dot" title={t("preview.badge")} aria-label={t("preview.badge")} />
          )}
        </div>
        <ol className="plan-steps">
          {steps.map((step, index) => (
            <li key={step.title} className={`plan-step ${step.state}`}>
              <span className="plan-marker" aria-hidden="true">
                {step.state === "done" ? "✓" : <span className="spinner small" />}
              </span>
              <span className="plan-body">
                <span className="plan-title">{step.title}</span>
                {step.meta && <span className="mono faint">{step.meta}</span>}
              </span>
              {index < steps.length - 1 && <span className="plan-line" aria-hidden="true" />}
            </li>
          ))}
        </ol>
      </section>

      {transcript.length === 0 && (
        <section className="panel-tools">
          <div className="section-head">
            <span className="section-title">{t("agent.toolCalls")}</span>
            <span className="preview-dot" title={t("preview.badge")} aria-label={t("preview.badge")} />
          </div>
          <div className="tool-chips">
            {AGENT_TOOL_CALLS.map((call) => (
              <span key={call.name} className="tool-chip">
                <span className="tone-ok" aria-hidden="true">✓</span>
                <span className="mono">{call.name}</span>
                <span className="mono faint truncate">{call.result}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      <Transcript transcript={transcript} busy={busy} variant="panel" />

      <Composer
        disabled={phase !== "ready"}
        busy={busy}
        inputRef={composerRef}
        onSend={onSend}
      />
    </aside>
  );
}
