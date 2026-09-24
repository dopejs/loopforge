import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { isDesktopRuntime } from "./agent";

/**
 * A question the agent is waiting on a person to answer.
 *
 * The model used to ask in its reply -- "A. ... B. ... C. ... Which?" -- and
 * the person answered by typing "A", guessing what that still meant to a model
 * that had moved on. Now asking is a tool call: it blocks, this renders it, and
 * what they choose becomes the call's result.
 *
 * Polled rather than read once, for the reason approvals are: the question
 * appears while a turn is already running, and a surface that looked only on
 * mount would show nothing while the call sat waiting.
 */
export type Question = {
  question_id: string;
  question: string;
  options: readonly { label: string; value: string }[];
  /** Whether they may answer in their own words as well. */
  allow_free_text: boolean;
  asked_at: string;
};

export type QuestionList = {
  schema_version: "loopforge-question-v1";
  questions: readonly Question[];
};

/**
 * How often to look.
 *
 * The call waits ten minutes, so this is about how long a question sits unseen
 * rather than about load. A second is imperceptible next to reading it.
 */
const POLL_INTERVAL_MS = 1000;

export function useQuestions(projectRoot: string, enabled: boolean): readonly Question[] {
  const [questions, setQuestions] = useState<readonly Question[]>([]);

  useEffect(() => {
    if (!enabled || !projectRoot || !isDesktopRuntime()) {
      setQuestions([]);
      return;
    }
    let cancelled = false;

    const read = async (): Promise<void> => {
      try {
        const list = await invoke<QuestionList>("agent_questions", {
          projectPath: projectRoot
        });
        if (!cancelled) setQuestions(list.questions ?? []);
      } catch {
        // The Agent may simply be starting. A poll that fails says nothing
        // worth showing, but it must not leave a question on screen that a
        // click can no longer answer.
        if (!cancelled) setQuestions([]);
      }
    };

    void read();
    const timer = window.setInterval(() => void read(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled, projectRoot]);

  return questions;
}

/** Answer one. The waiting call continues immediately. */
export function answerQuestion(
  projectRoot: string,
  questionId: string,
  answer: string
): Promise<QuestionList> {
  return invoke<QuestionList>("agent_answer_question", {
    projectPath: projectRoot,
    questionId,
    answer
  });
}
