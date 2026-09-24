"""The tool server's side of asking a person something.

Lives in the CLI package because that is what the tool server is, and it talks
to the Agent through the project directory rather than over the network: the
server runs under the `project_tools` sandbox profile, which denies network
outright. It has the project and nothing else, and the project is enough.

Deliberately thin. The file format belongs to `loopforge_agent.questions`,
which owns both the reading and the writing of the answer; this only writes a
question and watches for the reply.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..jsonutil import atomic_write_json

QUESTION_SCHEMA = "loopforge-question-v1"

#: Matches `loopforge_agent.questions.ANSWER_WAIT_SECONDS`. A person choosing
#: between options is slower than a person approving something they just read.
WAIT_SECONDS = 600.0

#: Often enough that a click feels immediate, rarely enough that ten minutes of
#: waiting is not thousands of reads of one small directory.
POLL_SECONDS = 0.5

MAX_OPTIONS = 6
MAX_OPTION_LENGTH = 120
MAX_QUESTION_LENGTH = 500

_SAFE_ID = re.compile(r"^ask_[A-Za-z0-9]{1,32}$")


class QuestionBridge:
    def __init__(self, project_root: Path) -> None:
        self.directory = Path(project_root) / ".loopforge" / "agent" / "questions"
        self.wait_seconds = WAIT_SECONDS
        self.poll_seconds = POLL_SECONDS

    def _path(self, question_id: str, suffix: str = "json") -> Path | None:
        if not _SAFE_ID.match(str(question_id)):
            return None
        return self.directory / f"{question_id}.{suffix}"

    def ask(self, question: Any, options: Any, allow_free_text: bool) -> dict[str, Any]:
        text = " ".join(str(question or "").split()).strip()[:MAX_QUESTION_LENGTH]
        if not text:
            raise ValueError("A question must say something.")
        choices: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in options if isinstance(options, list) else []:
            label = str(item.get("label") or item.get("value") or "") if isinstance(item, dict) else str(item)
            label = " ".join(label.split()).strip()
            if not label or len(label) > MAX_OPTION_LENGTH or label in seen:
                continue
            seen.add(label)
            choices.append({"label": label, "value": label})
            if len(choices) == MAX_OPTIONS:
                break
        record = {
            "schema_version": QUESTION_SCHEMA,
            "question_id": f"ask_{uuid.uuid4().hex[:16]}",
            "question": text,
            "options": choices,
            # A question with no options is still a question, so free text is
            # forced rather than refused: the alternative is a card nobody can
            # answer.
            "allow_free_text": bool(allow_free_text) or not choices,
            "asked_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._path(record["question_id"]), record)
        return record

    def answer_of(self, question_id: str) -> str | None:
        path = self._path(question_id, "answer.json")
        if path is None:
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Absent, or caught mid-write. Either way there is no answer yet.
            return None
        return str(record.get("answer", "")) if isinstance(record, dict) else None

    def withdraw(self, question_id: str) -> None:
        """Take an unanswered question off the screen when the call gives up."""
        for suffix in ("json", "answer.json"):
            path = self._path(question_id, suffix)
            if path is not None:
                path.unlink(missing_ok=True)
