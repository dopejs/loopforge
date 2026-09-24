"""Removing a conversation.

The store could always delete one; nothing exposed it, so a project filled up
with the conversations testing leaves behind and the only way to clear them was
to remove files by hand.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge_agent.application import LoopforgeAgent


class DeletingASession(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = LoopforgeAgent(self.root, kura_binary="/bin/false")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _session(self, text: str) -> str:
        from loopforge_agent.sessions import new_session_id

        session_id = new_session_id()
        self.agent.sessions_store.append(session_id, "user", text)
        return session_id

    def test_removes_the_conversation_it_names(self) -> None:
        keep = self._session("保留")
        drop = self._session("删掉")

        answer = self.agent.delete_session(drop)

        self.assertTrue(answer["deleted"])
        self.assertEqual([s["id"] for s in answer["sessions"]], [keep])

    def test_answers_with_what_is_left_rather_than_only_that_it_worked(self) -> None:
        # So a surface redraws from the Agent instead of from its own guess --
        # which is what two windows on the same project would disagree about.
        self._session("一")
        self._session("二")

        answer = self.agent.delete_session(self._session("三"))

        self.assertEqual(len(answer["sessions"]), 2)
        self.assertEqual(answer["schema_version"], "loopforge-session-v1")

    def test_the_conversation_is_gone_from_disk(self) -> None:
        session_id = self._session("删掉")
        self.agent.delete_session(session_id)

        with self.assertRaises(Exception):
            self.agent.session(session_id)

    def test_deleting_one_that_is_already_gone_is_reported_not_raised(self) -> None:
        # Two clicks on the same row, or a window that has not polled since
        # another deleted it. Both are people getting what they asked for.
        session_id = self._session("删掉")
        self.agent.delete_session(session_id)

        again = self.agent.delete_session(session_id)

        self.assertFalse(again["deleted"])
        self.assertEqual(again["sessions"], [])

    def test_an_id_from_outside_cannot_reach_outside_the_directory(self) -> None:
        # It arrives from a surface, and it removes a file.
        victim = self.root / "outside.json"
        victim.write_text("{}", encoding="utf-8")

        self.assertFalse(self.agent.delete_session("../outside")["deleted"])
        self.assertFalse(self.agent.delete_session("../../etc/passwd")["deleted"])
        self.assertTrue(victim.exists())

    def test_leaves_every_other_conversation_readable(self) -> None:
        keep = self._session("保留")
        self.agent.sessions_store.append(keep, "agent", "好的")
        self.agent.delete_session(self._session("删掉"))

        record = self.agent.session(keep)
        self.assertEqual([m["text"] for m in record["messages"]], ["保留", "好的"])


if __name__ == "__main__":
    unittest.main()
