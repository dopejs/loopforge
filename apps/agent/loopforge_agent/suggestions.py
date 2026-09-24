"""What is worth asking next, written by the model that did the work.

The workbench ships a fixed list keyed by stage, and it stays: it is instant,
it needs no provider, and it is the only thing that can answer on a fresh
install where nothing is configured yet. But it can only ever say generic
things. It cannot say "you wrote that the jump feel is the core -- want to
prototype that now?", because it has never read the project.

So the model writes them, at the two moments it costs nothing to ask:

  * when a turn ends, where it has just read the state and done the work, and
  * when a conversation is opened, where the project may have moved since.

Neither blocks anybody. A turn's reply is returned first and the suggestions
are generated behind it; an opened conversation renders the fixed list at once
and swaps in the generated set when it arrives. A person never waits on this,
which is what makes it safe to spend a model call on.

Failure is always silence. Nothing here raises into a turn: a suggestion that
cannot be generated leaves the fixed list showing, which is where this started.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loopforge.jsonutil import atomic_write_json

LOGGER = logging.getLogger(__name__)

SUGGESTION_SCHEMA = "loopforge-suggestion-v1"

#: Three fits the empty chat without becoming a menu. Asking for more and
#: truncating would drop the model's own ordering, which is the useful part.
WANTED = 3

#: Long enough to name a specific piece of work, short enough to read at a
#: glance in a button. Anything longer is a paragraph pretending to be a
#: prompt, and it is sent verbatim as the person's own message.
MAX_LENGTH = 60

#: The generation is a side errand, not the turn. A model that is slow enough
#: to matter here has already delivered the reply the person was waiting for.
TIMEOUT_SECONDS = 60.0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def fingerprint(context: Any, locale: str) -> str:
    """What the cached suggestions were written against.

    Suggestions go stale because the project moved, not because time passed, so
    this is what decides to regenerate rather than an age. The locale is part
    of it because generated text cannot be translated -- switching the
    interface language has to produce a new set, not a stale set in the
    language nobody is reading.
    """
    material = json.dumps(context, sort_keys=True, default=str) + "\0" + locale
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def clean(items: Any) -> list[str]:
    """The model's answer, reduced to what can be shown as a button.

    Deliberately forgiving about the envelope and strict about the contents. A
    model that wraps the list in prose or a code fence has still answered, and
    discarding that would mean showing nothing over formatting; but an entry
    that is empty, enormous, or a repeat is not a suggestion and no amount of
    parsing makes it one.
    """
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split()).strip()
        # Models like to number a list even when asked for JSON.
        text = re.sub(r"^\s*[-*•]\s*|^\s*\d+[.)]\s*", "", text).strip()
        if not text or len(text) > MAX_LENGTH:
            continue
        if text in out:
            continue
        out.append(text)
        if len(out) == WANTED:
            break
    return out


def parse(reply: str) -> list[str]:
    """Suggestions out of a reply that was asked for JSON and may not be.

    The bare array is tried first, then the first array anywhere in the text,
    because a fenced block or a sentence of preamble is the common way this
    comes back wrong and it is still a usable answer.
    """
    text = (reply or "").strip()
    if not text:
        return []
    try:
        return clean(json.loads(text))
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return clean(json.loads(match.group(0)))
    except json.JSONDecodeError:
        return []


class SuggestionStore:
    """The last generated set, per project.

    One file rather than a file per conversation: the suggestions describe
    where the project is, and the project has one state. A conversation opened
    tomorrow should see what the work looks like now, not what it looked like
    the last time that particular conversation was touched.
    """

    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".loopforge" / "agent" / "suggestions.json"

    def read(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Unreadable is the same as absent. The fixed list is behind this
            # and refusing to answer would show a person nothing at all.
            return None
        return value if isinstance(value, dict) else None

    def write(self, suggestions: list[str], fingerprint_value: str, locale: str) -> dict[str, Any]:
        record = {
            "schema_version": SUGGESTION_SCHEMA,
            "suggestions": suggestions,
            "fingerprint": fingerprint_value,
            "locale": locale,
            "generated_at": _now(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.path, record)
        except OSError as error:
            LOGGER.warning("suggestions were generated but not stored: %s", error)
        return record

    def matching(self, fingerprint_value: str) -> list[str]:
        """The stored set, if it was written against this state.

        A set written against a different state is not returned at all. Showing
        it would be worse than the fixed list: it is specific, so it reads as
        informed, and it would be confidently describing work that is done.
        """
        record = self.read()
        if not record or record.get("fingerprint") != fingerprint_value:
            return []
        stored = record.get("suggestions")
        return stored if isinstance(stored, list) else []
