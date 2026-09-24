"""Questions the agent is waiting on a person to answer.

The model used to ask by writing the question into its reply -- "A. I'll write
the Unity scripts  B. you already have code  C. start implementing. Which?" --
and the person answered by typing "A". That works only because they guessed
what "A" still meant to a model that had moved on, and it leaves nothing
structured behind: no record of what was offered, no way to render the choice,
and no way to tell a question from a paragraph that ends in one.

So asking is a tool call. The model calls `loopforge_ask`, the call blocks, the
question appears as a card with its options, and what the person chooses comes
back as the tool's result. The mechanics are the ones approvals already use --
a call held open until someone decides -- and the difference is that this one
returns what they said rather than whether they allowed it.

Handed over through the project directory rather than over the loopback API.
The tool server runs under the `project_tools` sandbox profile, which denies
network outright; it has the project directory and nothing else. Widening that
to reach one local port would trade a boundary that is currently absolute for a
convenience, and a directory both sides already hold is enough.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loopforge.jsonutil import atomic_write_json

QUESTION_SCHEMA = "loopforge-question-v1"

#: How long a call waits before giving up. Longer than an approval's three
#: minutes: approving is a yes/no about something just read, and this is a
#: choice a person has to think about. Not unbounded, because a turn nobody is
#: watching still has to end.
ANSWER_WAIT_SECONDS = 600.0

#: How many options a card can carry. A model asked for choices will otherwise
#: produce a menu, and a menu is the prose list this exists to replace.
MAX_OPTIONS = 6

#: Long enough for a real option, short enough to read on a button.
MAX_OPTION_LENGTH = 120
MAX_QUESTION_LENGTH = 500

#: A question that outlived the turn that asked it. Swept on read rather than
#: on a timer: nothing runs when the Agent is idle, and a stale card is only
#: wrong once somebody is looking at it.
STALE_AFTER_SECONDS = ANSWER_WAIT_SECONDS * 2

#: Files are named `<id>.json`; the id is generated here, but a traversal-proof
#: check keeps a malformed or hostile one from escaping the directory -- these
#: arrive from a subprocess and from a surface, not only from this module.
_SAFE_ID = re.compile(r"^ask_[A-Za-z0-9]{1,32}$")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_question_id() -> str:
    return f"ask_{uuid.uuid4().hex[:16]}"


def normalize_options(raw: Any) -> list[dict[str, str]]:
    """The options a card can show, out of whatever the model sent.

    Forgiving about the shape and strict about the contents: a model that sends
    plain strings has still answered, and rejecting that would turn a usable
    question into a failed tool call. But an option that is empty, enormous, or
    a repeat is not a choice, and offering it makes the card worse than the
    prose it replaces.
    """
    if not isinstance(raw, list):
        return []
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            label = value = item
        elif isinstance(item, dict):
            label = str(item.get("label") or item.get("value") or "")
            value = str(item.get("value") or item.get("label") or "")
        else:
            continue
        label = " ".join(label.split()).strip()
        value = " ".join(value.split()).strip()
        if not label or not value or len(label) > MAX_OPTION_LENGTH:
            continue
        if value in seen:
            continue
        seen.add(value)
        options.append({"label": label, "value": value})
        if len(options) == MAX_OPTIONS:
            break
    return options


def build(question: str, options: Any, allow_free_text: bool) -> dict[str, Any]:
    """One question, as it is written down and as it is rendered."""
    text = " ".join(str(question or "").split()).strip()[:MAX_QUESTION_LENGTH]
    if not text:
        raise ValueError("A question must say something.")
    choices = normalize_options(options)
    return {
        "schema_version": QUESTION_SCHEMA,
        "question_id": new_question_id(),
        "question": text,
        "options": choices,
        # A question with no options is still a question, so free text is
        # forced rather than refused: the alternative is a card nobody can
        # answer.
        "allow_free_text": bool(allow_free_text) or not choices,
        "asked_at": _now(),
    }


class QuestionDirectory:
    """Questions in flight, as files both sides can see.

    Two processes: the tool server writes a question and waits for an answer
    beside it; the Agent lists what is waiting and writes what the person
    chose. Separate files per question and per answer, so neither side ever
    rewrites what the other is reading.
    """

    def __init__(self, project_root: Path) -> None:
        self.directory = Path(project_root) / ".loopforge" / "agent" / "questions"

    def _path(self, question_id: str, suffix: str = "json") -> Path | None:
        if not _SAFE_ID.match(str(question_id)):
            return None
        return self.directory / f"{question_id}.{suffix}"

    def ask(self, record: dict[str, Any]) -> dict[str, Any]:
        path = self._path(record["question_id"])
        if path is None:
            raise ValueError("A question id must be one this module generated.")
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, record)
        return record

    def pending(self) -> list[dict[str, Any]]:
        """Everything still waiting, oldest first, stale ones swept."""
        try:
            files = sorted(self.directory.glob("ask_*.json"))
        except OSError:
            return []
        cutoff = time.time() - STALE_AFTER_SECONDS
        waiting: list[dict[str, Any]] = []
        for path in files:
            if path.name.endswith(".answer.json"):
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    continue
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # Half-written or vanished between the glob and the read. A
                # question that cannot be shown is one nobody can answer, and
                # the call waiting on it times out on its own.
                continue
            if isinstance(record, dict) and record.get("question_id"):
                waiting.append(record)
        return waiting

    def answer(self, question_id: str, answer: str) -> bool:
        """A person's choice. False if nothing was waiting on it."""
        question = self._path(question_id)
        if question is None or not question.exists():
            return False
        target = self._path(question_id, "answer.json")
        if target is None:
            return False
        atomic_write_json(target, {"question_id": question_id, "answer": str(answer or "")})
        # Removed after the answer is durable, so the waiter never sees the
        # question disappear with nothing beside it.
        question.unlink(missing_ok=True)
        return True

    def read_answer(self, question_id: str) -> str | None:
        path = self._path(question_id, "answer.json")
        if path is None:
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return str(record.get("answer", "")) if isinstance(record, dict) else None

    def withdraw(self, question_id: str) -> None:
        """Take it off the screen. A call that gave up cannot be answered."""
        for suffix in ("json", "answer.json"):
            path = self._path(question_id, suffix)
            if path is not None:
                path.unlink(missing_ok=True)
