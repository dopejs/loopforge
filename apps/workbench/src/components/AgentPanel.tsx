import React, { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { isDesktopRuntime } from "../agent";
import { useI18n } from "../i18n";
import { Markdown } from "./Markdown";
import { suggestionsFor } from "../suggestions";
import type { AgentPhase, AgentState, TranscriptEntry } from "../agent";

/**
 * The `@` mention being typed, if the caret is inside one.
 *
 * Returns where it starts and what has been typed after the `@`, so a
 * completion replaces the mention rather than appending to the message. A `@`
 * with a space after it is not a mention any more -- someone wrote an email
 * address or moved on -- and neither is one the caret has left.
 */
export function mentionAt(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const start = before.lastIndexOf("@");
  if (start === -1) return null;
  // Only at a word boundary: `user@host` is not someone asking for a file.
  if (start > 0 && !/\s/.test(before[start - 1])) return null;
  const query = before.slice(start + 1);
  if (/\s/.test(query)) return null;
  return { start, query };
}

export function Composer({
  disabled,
  busy,
  inputRef,
  projectRoot,
  onSend
}: {
  disabled: boolean;
  busy: boolean;
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
  /** Where to look for the files an `@` mention can complete to. */
  projectRoot?: string;
  onSend: (query: string) => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  /*
   * Whether an input method is mid-composition.
   *
   * Enter confirms a candidate while composing, and this sent the message
   * instead -- so anyone typing Chinese, Japanese or Korean sent a fragment of
   * a word every time they picked one. Not a corner case: it is every message
   * those users write.
   *
   * Two checks rather than one, because neither is sufficient here. The
   * platform webview on macOS is WKWebView, where `compositionend` fires
   * *after* the `keydown` that ended it -- so the flag is already false by the
   * time Enter is seen. `nativeEvent.isComposing` is still true on that event
   * and catches it. The flag covers engines that leave `isComposing` false
   * during composition and report `keyCode` 229 instead.
   */
  const composing = useRef(false);
  const own = useRef<HTMLTextAreaElement | null>(null);
  const box = inputRef ?? own;
  // The `@` mention under the caret, and what the project has that matches it.
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null);
  const [matches, setMatches] = useState<readonly string[]>([]);
  const [highlighted, setHighlighted] = useState(0);

  useEffect(() => {
    if (!mention || !projectRoot || !isDesktopRuntime()) {
      setMatches([]);
      return;
    }
    let cancelled = false;
    void invoke<string[]>("project_files", {
      projectPath: projectRoot,
      query: mention.query
    })
      .then((found) => {
        if (!cancelled) {
          setMatches(found.slice(0, 8));
          setHighlighted(0);
        }
      })
      // A listing that fails closes the menu rather than showing a stale one:
      // completing to a path that is no longer there is worse than not
      // completing.
      .catch(() => {
        if (!cancelled) setMatches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mention?.query, mention?.start, projectRoot]);

  /** Replace the mention being typed with a path. */
  const complete = (path: string): void => {
    if (!mention) return;
    const after = draft.slice(mention.start + 1 + mention.query.length);
    const next = `${draft.slice(0, mention.start)}@${path}${after.startsWith(" ") ? "" : " "}${after}`;
    setDraft(next);
    setMention(null);
    setMatches([]);
    // The caret belongs after what was just inserted, not at the end of a
    // message someone is still in the middle of writing.
    const caret = mention.start + 1 + path.length + 1;
    window.requestAnimationFrame(() => {
      box.current?.focus();
      box.current?.setSelectionRange(caret, caret);
    });
  };

  const track = (element: HTMLTextAreaElement): void => {
    setMention(mentionAt(element.value, element.selectionStart ?? element.value.length));
  };

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
      {/*
        The files an `@` can mean. Above the box rather than below it, because
        the box sits at the bottom of the window and a menu under it would open
        off screen.
      */}
      {matches.length > 0 && (
        <ul className="mentions" role="listbox" aria-label={t("agent.mentionFiles")}>
          {matches.map((path, index) => (
            <li key={path}>
              <button
                type="button"
                role="option"
                aria-selected={index === highlighted}
                className={index === highlighted ? "mention active" : "mention"}
                // `onMouseDown` rather than `onClick`: a click would blur the
                // textarea first, and the caret position it restores is the
                // one the completion depends on.
                onMouseDown={(event) => {
                  event.preventDefault();
                  complete(path);
                }}
              >
                {path}
              </button>
            </li>
          ))}
        </ul>
      )}
      <textarea
        ref={box}
        value={draft}
        rows={2}
        disabled={disabled}
        onChange={(event) => {
          setDraft(event.target.value);
          track(event.target);
        }}
        onClick={(event) => track(event.currentTarget)}
        onBlur={() => setMention(null)}
        onCompositionStart={() => {
          composing.current = true;
        }}
        onCompositionEnd={() => {
          composing.current = false;
        }}
        onKeyDown={(event) => {
          // The menu takes the keys it needs first. Enter completing a
          // highlighted path must not also send the message.
          if (matches.length > 0) {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setHighlighted((at) => (at + 1) % matches.length);
              return;
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setHighlighted((at) => (at - 1 + matches.length) % matches.length);
              return;
            }
            if (event.key === "Escape") {
              event.preventDefault();
              setMention(null);
              setMatches([]);
              return;
            }
            if (
              (event.key === "Enter" || event.key === "Tab") &&
              !event.nativeEvent.isComposing &&
              !composing.current
            ) {
              event.preventDefault();
              complete(matches[highlighted]);
              return;
            }
          }
          if (event.key !== "Enter") return;
          // Confirming a candidate, not sending a message.
          if (
            composing.current ||
            event.nativeEvent.isComposing ||
            event.nativeEvent.keyCode === 229
          ) {
            return;
          }
          // Enter sends; Shift+Enter and the platform modifiers insert a newline.
          if (!event.shiftKey && !event.metaKey && !event.ctrlKey) {
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
  variant,
  stage,
  onSuggest
}: {
  transcript: readonly TranscriptEntry[];
  busy: boolean;
  variant: "panel" | "page";
  /** Where the project is, so the suggestions are about the work it is up to. */
  stage?: string;
  /** Sends a suggestion. Absent means none are offered. */
  onSuggest?: (query: string) => void;
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
          {/*
            What is worth asking, where the project actually is.
            
            An empty chat that only says "how can I help?" leaves a person to
            guess, and the first thing they learn to say is `initialize the
            project` -- because that is what the agent answers a vague opening
            with. That is us teaching them to ask for our bookkeeping. They came
            to make a game.
          */}
          {onSuggest && (
            <div className="suggestions">
              {suggestionsFor(stage).map((key) => (
                <button
                  key={key}
                  type="button"
                  className="suggestion"
                  onClick={() => onSuggest(t(key))}
                >
                  {t(key)}
                </button>
              ))}
            </div>
          )}
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
          {/*
            The user's own words are shown as typed; the Agent's are Markdown.
            Rendering what the user wrote would reinterpret their input, and
            they are the one person here who did not mean any of it as markup.
          */}
          <div className="message-text">
            {entry.author === "user" ? entry.text : <Markdown>{entry.text}</Markdown>}
            {entry.streaming && <span className="caret" aria-hidden="true" />}
          </div>
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
