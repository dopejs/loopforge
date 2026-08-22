"""Conversation history, owned by the Loopforge Agent.

Kura's `/v1/chat/query` is stateless: it creates no thread and returns no
identifier, so nothing upstream remembers a conversation. `docs/architecture.md`
places sessions in the Agent layer anyway ("owns project context, sessions,
planning"), so history is stored here rather than projected from the runtime.

Sessions live beside the rest of the Agent's per-project state so they travel
with the project and are removed with it. Each session is a separate file: a
single index would have to be rewritten on every message, which turns an
interrupted write into the loss of every conversation rather than one.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loopforge.jsonutil import atomic_write_json

SESSION_SCHEMA = "loopforge-session-v1"
MAX_SESSIONS = 200
MAX_MESSAGES = 500
#: Long enough to identify a conversation in a sidebar, short enough to store.
TITLE_LIMIT = 80

#: Session files are named `<id>.json`; the id is generated here, but a
#: traversal-proof check keeps a malformed or hostile id from escaping the
#: directory if one ever arrives from outside.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_session_id() -> str:
    """A sortable, collision-resistant session id."""
    return f"ses_{uuid.uuid4().hex[:16]}"


def derive_title(text: str) -> str:
    """A session's title is its opening request, collapsed to one line."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= TITLE_LIMIT:
        return collapsed
    return collapsed[: TITLE_LIMIT - 1].rstrip() + "…"


class SessionStore:
    """Per-project conversation history."""

    def __init__(self, project_root: Path) -> None:
        self.directory = project_root / ".loopforge" / "agent" / "sessions"

    # -- reads --------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """Sessions, most recently updated first.

        A file that cannot be read is skipped rather than failing the listing:
        one corrupt session must not hide the rest.
        """
        if not self.directory.is_dir():
            return []
        sessions = []
        for path in self.directory.glob("*.json"):
            record = self._read(path)
            if record is None:
                continue
            sessions.append(
                {
                    "id": record["id"],
                    "title": record.get("title", ""),
                    "updated_at": record.get("updated_at", ""),
                    "message_count": len(record.get("messages", [])),
                }
            )
        sessions.sort(key=lambda item: item["updated_at"], reverse=True)
        return sessions[:MAX_SESSIONS]

    def read(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        return None if path is None else self._read(path)

    # -- writes -------------------------------------------------------------

    def append(self, session_id: str, author: str, text: str) -> dict[str, Any]:
        """Append a message, creating the session on first use.

        Returns the stored session so a caller can surface its title without a
        second read.
        """
        path = self._path(session_id)
        if path is None:
            raise ValueError(f"invalid session id: {session_id!r}")
        record = self._read(path) or {
            "schema_version": SESSION_SCHEMA,
            "id": session_id,
            "title": "",
            "created_at": _now(),
            "messages": [],
        }
        messages = record.setdefault("messages", [])
        messages.append({"author": author, "text": text, "at": _now()})
        # Bound the file so a long-running conversation cannot grow without
        # limit; the oldest turns are dropped first.
        if len(messages) > MAX_MESSAGES:
            del messages[: len(messages) - MAX_MESSAGES]
        if not record.get("title") and author == "user":
            record["title"] = derive_title(text)
        record["updated_at"] = _now()
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, record)
        return record

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if path is None or not path.is_file():
            return False
        path.unlink()
        return True

    # -- internals ----------------------------------------------------------

    def _path(self, session_id: str) -> Path | None:
        if not _SAFE_ID.match(session_id or ""):
            return None
        return self.directory / f"{session_id}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            return None
        return record
