import React, { useState } from "react";
import { useI18n } from "../i18n";
import { errorMessage } from "../daemon";
import { type Question, answerQuestion, useQuestions } from "../questions";

/**
 * What the agent needs to know, asked where the asking happened.
 *
 * The model used to write the choices into its reply -- "A. I'll write the
 * Unity scripts  B. you already have code  C. start implementing. Which?" --
 * and the person answered by typing "A". That works only if they guess what
 * the letter still means to a model that has moved on, and it leaves nothing a
 * surface can render: a question is indistinguishable from a paragraph that
 * ends in one.
 *
 * Now asking is a tool call. It blocks, this draws it, and what they choose
 * becomes the call's result -- so the model is told what they picked rather
 * than parsing it back out of the next message.
 */
function Asked({
  question,
  projectRoot,
  onAnswered
}: {
  question: Question;
  projectRoot: string;
  onAnswered: () => void;
}): React.JSX.Element {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [failure, setFailure] = useState<string>();

  const answer = async (value: string): Promise<void> => {
    const chosen = value.trim();
    if (busy || !chosen) return;
    setBusy(true);
    setFailure(undefined);
    try {
      await answerQuestion(projectRoot, question.question_id, chosen);
      onAnswered();
    } catch (error: unknown) {
      setFailure(errorMessage(error, t("question.failed")));
      setBusy(false);
    }
  };

  return (
    <article className="question" aria-live="assertive">
      <header className="question-head">
        <span className="badge accent">{t("question.waiting")}</span>
      </header>
      <p className="question-text">{question.question}</p>
      {question.options.length > 0 && (
        <div className="question-options">
          {question.options.map((option) => (
            <button
              key={option.value}
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => void answer(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
      {/*
        Offered alongside the options, not instead of them. A named option is
        rarely the whole of what someone means, and a card that only takes the
        answers the model thought of is a worse question than an open one.
      */}
      {question.allow_free_text && (
        <form
          className="question-free"
          onSubmit={(event) => {
            event.preventDefault();
            void answer(draft);
          }}
        >
          <input
            type="text"
            value={draft}
            disabled={busy}
            placeholder={t("question.freeText")}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button type="submit" className="primary-button" disabled={busy || !draft.trim()}>
            {busy ? t("question.answering") : t("question.answer")}
          </button>
        </form>
      )}
      {failure && <p className="issue-line">{failure}</p>}
    </article>
  );
}

export function QuestionCard({
  projectRoot,
  enabled
}: {
  projectRoot: string;
  /** Only while the Agent could be running; polling a dead one says nothing. */
  enabled: boolean;
}): React.JSX.Element | null {
  const questions = useQuestions(projectRoot, enabled);
  // Answered questions disappear on the next poll. Tracking them here as well
  // keeps the buttons from sitting live for the second it takes to notice.
  const [answered, setAnswered] = useState<readonly string[]>([]);
  const waiting = questions.filter((item) => !answered.includes(item.question_id));

  if (waiting.length === 0) return null;

  return (
    <div className="questions">
      {waiting.map((question) => (
        <Asked
          key={question.question_id}
          question={question}
          projectRoot={projectRoot}
          onAnswered={() => setAnswered((seen) => [...seen, question.question_id])}
        />
      ))}
    </div>
  );
}
