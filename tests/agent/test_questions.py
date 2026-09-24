"""Asking a person something, as a tool call rather than as prose.

The model used to ask by writing the choices into its reply -- "A. I'll write
the Unity scripts  B. you already have code  C. start implementing. Which?" --
and the person answered by typing "A", guessing what that still meant to a
model that had moved on. Nothing structured was left: no record of what was
offered, and no way for a surface to tell a question from a paragraph.

Two processes are involved. The tool server writes the question into the
project and waits beside it; the Agent lists what is waiting and writes what
the person chose. They never share memory, and the tool server has no network
at all -- its sandbox profile denies it.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from loopforge.agent.questions_bridge import QuestionBridge
from loopforge_agent import questions as kit
from loopforge_agent.application import LoopforgeAgent


class Options(unittest.TestCase):
    def test_takes_plain_strings_a_model_is_likely_to_send(self) -> None:
        # Rejecting these would turn a usable question into a failed tool call.
        self.assertEqual(
            kit.normalize_options(["Unity", "Godot"]),
            [{"label": "Unity", "value": "Unity"}, {"label": "Godot", "value": "Godot"}],
        )

    def test_drops_what_cannot_be_a_button(self) -> None:
        parsed = kit.normalize_options(["", "x" * 400, "同一个", "同一个", 42, "好"])
        self.assertEqual([o["label"] for o in parsed], ["同一个", "好"])

    def test_keeps_a_menu_from_forming(self) -> None:
        # A model asked for choices will produce a list, and a long list is the
        # prose menu this exists to replace.
        self.assertEqual(len(kit.normalize_options([f"o{n}" for n in range(20)])), kit.MAX_OPTIONS)

    def test_a_question_with_no_options_still_takes_an_answer(self) -> None:
        # Otherwise it is a card nobody can answer.
        self.assertTrue(kit.build("什么引擎？", [], False)["allow_free_text"])

    def test_refuses_a_question_that_says_nothing(self) -> None:
        with self.assertRaises(ValueError):
            kit.build("   ", ["a"], True)


class RoundTrip(unittest.TestCase):
    """The tool server and the Agent, through the project directory."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = LoopforgeAgent(self.root, kura_binary="/bin/false")
        self.bridge = QuestionBridge(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_question_asked_by_the_tool_reaches_the_agent(self) -> None:
        self.bridge.ask("用什么引擎？", ["Unity", "Godot"], False)

        waiting = self.agent.questions()["questions"]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["question"], "用什么引擎？")
        self.assertEqual([o["label"] for o in waiting[0]["options"]], ["Unity", "Godot"])

    def test_an_answer_reaches_the_tool_that_is_waiting(self) -> None:
        # The whole point: the person's choice becomes the tool's result, so
        # the model is told what they picked rather than left to parse it back
        # out of the next message.
        record = self.bridge.ask("用什么引擎？", ["Unity", "Godot"], False)

        self.agent.answer_question(record["question_id"], "Unity")

        self.assertEqual(self.bridge.answer_of(record["question_id"]), "Unity")

    def test_answering_takes_the_card_off_the_screen(self) -> None:
        record = self.bridge.ask("用什么引擎？", ["Unity"], False)
        self.agent.answer_question(record["question_id"], "Unity")

        self.assertEqual(self.agent.questions()["questions"], [])

    def test_a_second_answer_is_reported_rather_than_written(self) -> None:
        # The card may have gone between being drawn and being clicked. Telling
        # someone off for answering too slowly helps nobody, but overwriting an
        # answer the model already acted on would be worse.
        record = self.bridge.ask("用什么引擎？", ["Unity"], False)
        self.agent.answer_question(record["question_id"], "Unity")

        second = self.agent.answer_question(record["question_id"], "Godot")

        self.assertFalse(second["delivered"])
        self.assertEqual(self.bridge.answer_of(record["question_id"]), "Unity")

    def test_an_id_from_outside_cannot_reach_outside_the_directory(self) -> None:
        # These arrive from a subprocess and from a surface, not only from the
        # module that generates them.
        self.assertFalse(self.agent.answer_question("../../../etc/passwd", "x")["delivered"])
        self.assertFalse(self.agent.answer_question("ask_../escape", "x")["delivered"])

    def test_the_waiting_call_sees_an_answer_given_while_it_waits(self) -> None:
        # The real sequence: the tool blocks, the card is drawn, someone
        # clicks, and the call comes back with what they chose.
        record = self.bridge.ask("用什么引擎？", ["Unity", "Godot"], False)
        answered: list[str | None] = []

        def wait() -> None:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                answer = self.bridge.answer_of(record["question_id"])
                if answer is not None:
                    answered.append(answer)
                    return
                time.sleep(0.05)
            answered.append(None)

        waiter = threading.Thread(target=wait)
        waiter.start()
        time.sleep(0.2)
        self.agent.answer_question(record["question_id"], "Godot")
        waiter.join(timeout=6)

        self.assertEqual(answered, ["Godot"])

    def test_a_withdrawn_question_stops_being_shown(self) -> None:
        # A call that gave up leaves a card that can no longer be answered.
        record = self.bridge.ask("用什么引擎？", ["Unity"], False)
        self.bridge.withdraw(record["question_id"])

        self.assertEqual(self.agent.questions()["questions"], [])

    def test_a_question_nobody_ever_answered_is_swept(self) -> None:
        # Nothing runs while the Agent is idle, so this happens on read. A card
        # from a conversation that ended yesterday must not greet someone.
        record = self.bridge.ask("用什么引擎？", ["Unity"], False)
        stale = self.root / ".loopforge" / "agent" / "questions" / f"{record['question_id']}.json"
        old = time.time() - kit.STALE_AFTER_SECONDS - 60
        import os

        os.utime(stale, (old, old))

        self.assertEqual(self.agent.questions()["questions"], [])
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
