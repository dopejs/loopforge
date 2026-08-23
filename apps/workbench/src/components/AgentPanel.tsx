import React, { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import type { AgentPhase, AgentState, TranscriptEntry } from "../agent";

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
          <p className="message-text">
            {entry.text}
            {entry.streaming && <span className="caret" aria-hidden="true" />}
          </p>
        </article>
      ))}
      {busy && !transcript.some((entry) => entry.streaming) && (
        <p className="message-pending">
          <span className="spinner" aria-hidden="true" />
          {t("agent.status.working")}
        </p>
      )}
      <div ref={end} />
    </div>
  );
}

/**
 * Shortcuts the composer inserts into the draft.
 *
 * Kept here rather than with the preview fixtures: these do something -- each
 * one appends itself to what the user is typing -- and living alongside
 * made-up canvas data made a working affordance look like a mock-up.
 */
const COMPOSER_CHIPS = ["@file", "/test", "/playtest"] as const;

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
  // No invented fallback: the Agent either reported next actions or it did
  // not, and a plan the user never asked for reads as work in progress.
  const steps = nextActions.map((title) => ({ title, meta: "", state: "done" as const }));

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
          {/* A run id is shown once there is a run. Inventing one made the
              panel look like it was tracking work that did not exist. */}
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
      {realPlan && (
      <section className="panel-plan">
        <div className="section-head">
          <span className="section-title">{t("agent.plan")}</span>
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
