"""Suggestions written by the model that did the work.

The workbench ships a fixed list keyed by stage. It is instant, needs no
provider, and is the only thing that can answer on a fresh install -- but it
has never read the project, so it can only ever say generic things. These are
generated at the two moments it costs nobody any waiting: when a turn ends, and
when a conversation is opened.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from loopforge_agent import suggestions as kit
from loopforge_agent.application import LoopforgeAgent


class Parsing(unittest.TestCase):
    def test_reads_the_bare_array(self) -> None:
        self.assertEqual(kit.parse('["a", "b"]'), ["a", "b"])

    def test_reads_an_array_a_model_wrapped_in_prose(self) -> None:
        # Asking for JSON gets JSON most of the time. Discarding the rest would
        # mean showing nothing over formatting, when the answer is right there.
        self.assertEqual(
            kit.parse('Sure!\n```json\n["做个原型", "试玩一次"]\n```'),
            ["做个原型", "试玩一次"],
        )

    def test_keeps_at_most_what_fits_in_the_empty_chat(self) -> None:
        self.assertEqual(len(kit.parse(json.dumps([f"s{n}" for n in range(9)]))), kit.WANTED)

    def test_drops_what_cannot_be_a_button(self) -> None:
        # Empty, enormous, or a repeat. None of these is a suggestion and no
        # amount of parsing makes one.
        parsed = kit.parse(json.dumps(["", "x" * 400, "同一条", "同一条", "好的"]))
        self.assertEqual(parsed, ["同一条", "好的"])

    def test_strips_the_numbering_a_model_adds_anyway(self) -> None:
        self.assertEqual(kit.parse('["1. 做个原型", "- 试玩"]'), ["做个原型", "试玩"])

    def test_answers_nothing_for_a_reply_that_is_not_a_list(self) -> None:
        # Silence, rather than a guess. The fixed list is behind this.
        self.assertEqual(kit.parse("I could not think of any."), [])
        self.assertEqual(kit.parse(""), [])


class Freshness(unittest.TestCase):
    """Suggestions go stale because the project moved, not because time passed."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = kit.SuggestionStore(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_returns_what_was_written_against_this_state(self) -> None:
        mark = kit.fingerprint({"stage": "DISCOVERY"}, "zh-Hans")
        self.store.write(["做个原型"], mark, "zh-Hans")
        self.assertEqual(self.store.matching(mark), ["做个原型"])

    def test_withholds_what_was_written_against_an_older_state(self) -> None:
        # Worse than the fixed list, not better: a stale suggestion is
        # specific, so it reads as informed, and it would confidently propose
        # work that is already finished.
        self.store.write(["做个原型"], kit.fingerprint({"stage": "DISCOVERY"}, "en"), "en")
        moved = kit.fingerprint({"stage": "PROTOTYPING"}, "en")
        self.assertEqual(self.store.matching(moved), [])

    def test_a_change_of_language_is_a_change_of_state(self) -> None:
        # Generated text cannot be translated. Switching the interface has to
        # produce a new set, not a stale set nobody can read.
        context = {"stage": "DISCOVERY"}
        self.store.write(["prototype it"], kit.fingerprint(context, "en"), "en")
        self.assertEqual(self.store.matching(kit.fingerprint(context, "ja")), [])

    def test_an_unreadable_file_is_the_same_as_none(self) -> None:
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(self.store.matching("anything"), [])


class Generation(unittest.TestCase):
    """The Agent's two triggers, without a model behind them."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = LoopforgeAgent(self.root, kura_binary="/bin/false")
        self.dispatched: list[dict] = []
        # `_answer` replaces a module global. Kept so tearDown can put it back:
        # a fake left behind is one every later test unknowingly talks to.
        import loopforge_agent.application as module

        self.module = module
        self.real_client = module.KuraClient

    def tearDown(self) -> None:
        # Before the directory goes, and before the next test patches the
        # client out from under it. A generation started here outlives the
        # test that started it, and it was dispatching into the next test's
        # record -- which read as the turn-end trigger having lost its turn.
        self._settle()
        self.module.KuraClient = self.real_client
        self.temporary.cleanup()

    def _answer(self, reply: str, delay: float = 0.0):
        """Stand in for the runtime, recording what was dispatched."""
        agent = self.agent
        agent.runtime.status = lambda: {  # type: ignore[method-assign]
            "healthy": True,
            "base_url": "http://127.0.0.1:1",
            "token": "t",
        }
        dispatched = self.dispatched

        class Client:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def post(self, path, body):
                dispatched.append({"path": path, "body": body})
                if delay:
                    time.sleep(delay)
                return {"reply": reply}

        import loopforge_agent.application as module

        module.KuraClient = Client  # type: ignore[assignment]
        return agent

    def _settle(self) -> None:
        for thread in threading.enumerate():
            if thread.name == "loopforge-suggestions":
                thread.join(timeout=10)

    def test_generates_without_offering_the_model_any_tools(self) -> None:
        # The one that matters. This dispatch is on nobody's behalf, and a
        # background turn that reached an approval-gated tool would raise "may
        # the agent initialize this project?" at a person who asked for
        # nothing. The context is handed to it, so it needs no tools at all.
        agent = self._answer('["做个原型"]')
        agent.suggestions("zh-Hans")
        self._settle()

        self.assertEqual(len(self.dispatched), 1)
        self.assertIs(self.dispatched[0]["body"]["withoutTools"], True)

    def test_does_not_join_anybody_s_conversation(self) -> None:
        # A thread id would put this in someone's history and pull theirs in
        # as context.
        agent = self._answer('["做个原型"]')
        agent.suggestions("en")
        self._settle()

        self.assertNotIn("threadId", self.dispatched[0]["body"])

    def test_asks_in_the_language_the_window_is_reading(self) -> None:
        agent = self._answer('["做个原型"]')
        agent.suggestions("zh-Hans")
        self._settle()

        self.assertIn("zh-Hans", self.dispatched[0]["body"]["query"])

    def test_serves_the_generated_set_on_the_next_read(self) -> None:
        agent = self._answer('["做个原型", "试玩一次"]')
        first = agent.suggestions("zh-Hans")
        # Nothing yet, and that is the contract: the caller renders its fixed
        # list rather than waiting.
        self.assertEqual(first["suggestions"], [])
        self.assertTrue(first["generating"])
        self._settle()

        second = agent.suggestions("zh-Hans")
        self.assertEqual(second["suggestions"], ["做个原型", "试玩一次"])
        self.assertFalse(second["generating"])
        # And it does not pay for the same answer twice.
        self.assertEqual(len(self.dispatched), 1)

    def test_refreshes_the_access_token_before_dispatching(self) -> None:
        # This can run long after the turn that scheduled it -- a conversation
        # opened in the morning generates against a token seeded the night
        # before -- and an access token lasts about an hour. A stale one comes
        # back as an authentication error, which here is silent: the fixed list
        # would simply never be replaced, with nothing saying why.
        agent = self._answer('["做个原型"]')
        synced: list[int] = []
        agent.sync_provider_credential = lambda: synced.append(1)  # type: ignore[method-assign]

        agent.suggestions("en")
        self._settle()

        self.assertEqual(len(synced), 1)

    def test_a_turn_ending_generates_from_what_just_happened(self) -> None:
        agent = self._answer('["接着做碰撞"]')
        agent._suggest_after_turn("帮我做个原型", "我建好了跳跃")
        self._settle()

        self.assertEqual(len(self.dispatched), 1)
        sent = self.dispatched[0]["body"]["query"]
        self.assertIn("帮我做个原型", sent)
        self.assertIn("我建好了跳跃", sent)

    def test_two_triggers_at_once_cost_one_generation(self) -> None:
        # A turn ends in one window while another opens a conversation. Two
        # model calls writing one file is twice the cost for one answer.
        agent = self._answer('["做个原型"]', delay=0.4)
        agent.suggestions("en")
        agent._suggest_after_turn("q", "a")
        agent.suggestions("en")
        self._settle()

        self.assertEqual(len(self.dispatched), 1)

    def test_a_failing_generation_is_silent(self) -> None:
        # It runs behind a reply that has already been delivered. Anything
        # raised here would turn a finished answer into a failed request.
        agent = self._answer('["ok"]')

        class Exploding:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def post(self, path, body):
                raise RuntimeError("the provider is down")

        import loopforge_agent.application as module

        module.KuraClient = Exploding  # type: ignore[assignment]
        agent._suggest_after_turn("q", "a")
        self._settle()

        self.assertEqual(agent.suggestions("en")["suggestions"], [])

    def test_says_nothing_is_coming_when_the_runtime_is_down(self) -> None:
        # So a surface polling for a generated set does not poll forever for
        # something nobody is writing.
        self.agent.runtime.status = lambda: {"healthy": False}  # type: ignore[method-assign]
        self._settle()

        answer = self.agent.suggestions("en")
        self.assertEqual(answer["suggestions"], [])
        # The assertion this test exists for. Reporting a generation that is
        # not happening leaves a surface waiting on it for the life of the
        # window.
        self.assertFalse(answer["generating"])


if __name__ == "__main__":
    unittest.main()
