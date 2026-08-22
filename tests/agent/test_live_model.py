"""Drafting against a real model.

Every other test that touches drafting uses Kura's built-in `echo` provider,
which returns the prompt. That proves the pipeline carries a request and parses
a reply, and says nothing about the thing the feature actually promises: that
what comes back is a usable draft a person can edit rather than start from.

Opt in by setting LOOPFORGE_TEST_LLM_BASE_URL, _API_KEY and _MODEL. Skipped
otherwise, so CI and a developer without credentials stay green.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject
from tests.support.kura_daemon import KuraDaemon, requires_kura, requires_live_provider

#: A real model may drop a section. The draft is edited before submission, so a
#: near-complete answer is a success; the failure this guards against is a
#: reply the parser cannot use at all.
MINIMUM_ANSWERED_FIELDS = 8

BRIEF = (
    "A 2D single-screen game where charging an attack near moving hazards "
    "multiplies the score."
)


@requires_kura
@requires_live_provider
class LiveDraftTests(unittest.TestCase):
    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon(live=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _agent(self):
        from loopforge_agent.application import LoopforgeAgent

        daemon = self.daemon
        root = Path(tempfile.mkdtemp(prefix="lf-live-"))
        agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {
                    "healthy": True,
                    "base_url": daemon.base_url,
                    "token": daemon.token,
                }

            def sync_context(self) -> dict:
                return {"context": {"schema_version": "game-project-context-v1"}}

        agent.runtime = _Runtime()
        agent.project = LoopforgeProject(root)
        agent.project.init()
        return agent

    def test_the_configured_provider_is_registered(self) -> None:
        """Runs before the rest and fails with the inventory in hand.

        Kura registers the OpenAI-compatible endpoint only when it is
        configured, so a missing override shows up here as an absent provider
        rather than downstream as an opaque dispatch failure.
        """
        inventory = self.daemon.client(timeout=60).get("/v1/providers")
        registered = {
            str(item.get("providerId") or "") for item in inventory.get("items") or []
        }
        self.assertIn("openai_compatible", registered, f"registered: {sorted(registered)}")

    def test_the_provider_answers_at_all(self) -> None:
        """Fails first and clearly when the credential or model is wrong,
        rather than leaving the drafting tests to fail for an unclear reason."""
        reply = self.daemon.client(timeout=180).post(
            "/v1/chat/query", {"query": "Reply with exactly: OK"}
        )
        self.assertTrue(str(reply.get("reply", "")).strip())

    def test_a_hypothesis_draft_comes_back_usable(self) -> None:
        """The claim the feature makes: the user edits a draft rather than
        filling eleven empty boxes."""
        agent = self._agent()

        draft = agent.draft_hypothesis(BRIEF)

        answered = [key for key in HYPOTHESIS_FIELDS if draft["fields"][key].strip()]
        self.assertGreaterEqual(
            len(answered),
            MINIMUM_ANSWERED_FIELDS,
            f"only {len(answered)} of {len(HYPOTHESIS_FIELDS)} sections parsed: "
            f"missing {draft['missing']}",
        )
        # Content, not an echo of the heading it sits under.
        for key in answered:
            value = draft["fields"][key].strip()
            self.assertNotEqual(value.lower(), key.replace("_", " "))
            self.assertGreater(len(value), 10, key)
        # Still a proposal: nothing reached the project.
        self.assertFalse(agent.hypothesis()["present"])

    def test_a_complete_draft_is_accepted_by_the_core(self) -> None:
        """End of the path. A draft that parses but the core rejects would be
        no better than a blank form."""
        agent = self._agent()
        draft = agent.draft_hypothesis(BRIEF)
        fields = dict(draft["fields"])
        # Fill only what the model left out, so what is submitted is
        # substantially the model's own work.
        filled = [key for key in HYPOTHESIS_FIELDS if not fields[key].strip()]
        for key in filled:
            fields[key] = f"Supplied by the operator: {key.replace('_', ' ')}."

        recorded = agent.create_hypothesis(
            fields,
            approver_id="op_live",
            approver_name="Local Operator",
            rationale="Reviewed the drafted hypothesis.",
        )

        self.assertTrue(recorded["present"])
        self.assertEqual(recorded["missing"], [])
        gate = {
            item["code"]: item["status"]
            for item in agent.gate("PROTOTYPING")["requirements"]
        }
        self.assertEqual(gate["HYPOTHESIS_COMPLETE"], "satisfied")

    def test_a_playtest_protocol_draft_is_prose_a_facilitator_can_use(self) -> None:
        agent = self._agent()
        agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS},
            approver_id="op_live",
            approver_name="Local Operator",
            rationale="Reviewed.",
        )

        draft = agent.draft_playtest_protocol()

        content = draft["content"].strip()
        self.assertTrue(draft["draft"])
        # Long enough to be instructions rather than a refusal or a one-liner.
        self.assertGreater(len(content), 200, content[:200])
        # The skill is supplied in the prompt; echoing it back is not an answer.
        self.assertNotIn("</loopforge_internal_skill>", content)


if __name__ == "__main__":
    unittest.main()
