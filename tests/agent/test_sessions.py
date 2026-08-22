"""Session storage: conversation history the Agent owns."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from loopforge_agent.sessions import (
    MAX_MESSAGES,
    SessionStore,
    derive_title,
    new_session_id,
)


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="loopforge-sessions-"))
        self.store = SessionStore(self.root)

    def test_listing_an_unused_project_is_empty_not_an_error(self) -> None:
        self.assertEqual(self.store.list(), [])

    def test_append_creates_then_extends_a_session(self) -> None:
        session_id = new_session_id()
        self.store.append(session_id, "user", "tune the boss")
        self.store.append(session_id, "agent", "done")

        record = self.store.read(session_id)
        assert record is not None
        self.assertEqual([m["author"] for m in record["messages"]], ["user", "agent"])
        self.assertEqual(record["title"], "tune the boss")

    def test_title_comes_from_the_opening_request_only(self) -> None:
        session_id = new_session_id()
        self.store.append(session_id, "user", "first question")
        self.store.append(session_id, "user", "second question")
        record = self.store.read(session_id)
        assert record is not None
        # A later message must not rename an existing conversation.
        self.assertEqual(record["title"], "first question")

    def test_titles_collapse_whitespace_and_are_bounded(self) -> None:
        self.assertEqual(derive_title("a\n\n  b\tc"), "a b c")
        long_title = derive_title("x" * 200)
        self.assertLessEqual(len(long_title), 80)
        self.assertTrue(long_title.endswith("…"))

    def test_listing_is_ordered_by_recency(self) -> None:
        import time

        first, second = new_session_id(), new_session_id()
        self.store.append(first, "user", "older")
        time.sleep(1.05)  # timestamps have second resolution
        self.store.append(second, "user", "newer")
        self.assertEqual([s["id"] for s in self.store.list()], [second, first])

    def test_history_is_bounded(self) -> None:
        session_id = new_session_id()
        for index in range(MAX_MESSAGES + 20):
            self.store.append(session_id, "user", f"message {index}")
        record = self.store.read(session_id)
        assert record is not None
        self.assertEqual(len(record["messages"]), MAX_MESSAGES)
        # The oldest turns are dropped, so the newest survive.
        self.assertEqual(record["messages"][-1]["text"], f"message {MAX_MESSAGES + 19}")

    def test_a_corrupt_session_is_skipped_not_fatal(self) -> None:
        good = new_session_id()
        self.store.append(good, "user", "readable")
        (self.store.directory / "broken.json").write_text("{not json", encoding="utf-8")

        listed = [s["id"] for s in self.store.list()]
        self.assertEqual(listed, [good])

    def test_ids_that_could_escape_the_directory_are_refused(self) -> None:
        for hostile in ["../escape", "a/b", "", "..", "x" * 65]:
            with self.assertRaises(ValueError):
                self.store.append(hostile, "user", "x")
            self.assertIsNone(self.store.read(hostile))
            self.assertFalse(self.store.delete(hostile))

    def test_delete_removes_a_session_and_is_safe_to_repeat(self) -> None:
        session_id = new_session_id()
        self.store.append(session_id, "user", "x")
        self.assertTrue(self.store.delete(session_id))
        self.assertFalse(self.store.delete(session_id))
        self.assertEqual(self.store.list(), [])

    def test_sessions_are_separate_files(self) -> None:
        """One index would have to be rewritten on every message, so an
        interrupted write would lose every conversation instead of one."""
        first, second = new_session_id(), new_session_id()
        self.store.append(first, "user", "a")
        self.store.append(second, "user", "b")
        files = sorted(p.name for p in self.store.directory.glob("*.json"))
        self.assertEqual(files, sorted([f"{first}.json", f"{second}.json"]))
        payload = json.loads((self.store.directory / f"{first}.json").read_text())
        self.assertEqual(payload["schema_version"], "loopforge-session-v1")


if __name__ == "__main__":
    unittest.main()
