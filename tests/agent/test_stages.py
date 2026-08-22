"""Gate checks and stage transitions as the Agent projects them."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError

APPROVAL = {
    "approver_id": "op_local",
    "approver_name": "Local Operator",
    "rationale": "Reviewed; the keep and kill signals are observable.",
}


class StageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)
        self.agent.project.init()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _statuses(self, stage: str = "PROTOTYPING") -> dict[str, str]:
        return {r["code"]: r["status"] for r in self.agent.gate(stage)["requirements"]}

    def _record_hypothesis(self, approved: bool = True) -> None:
        fields = {key: f"value {key}" for key in HYPOTHESIS_FIELDS}
        self.agent.create_hypothesis(fields, **(APPROVAL if approved else {}))

    def test_a_blocked_gate_names_every_unmet_requirement(self) -> None:
        result = self.agent.gate("PROTOTYPING")
        self.assertEqual(result["schema_version"], "loopforge-gate-v1")
        self.assertEqual(result["result"], "blocked")
        self.assertEqual(result["from_stage"], "DISCOVERY")
        self.assertEqual(
            self._statuses(),
            {
                "HYPOTHESIS_PRESENT": "missing",
                "HYPOTHESIS_COMPLETE": "missing",
                "HUMAN_APPROVAL": "missing",
            },
        )
        # Remediation text travels with each requirement; without it the
        # surface can only show a code.
        self.assertTrue(all(r["message"] for r in result["requirements"]))

    def test_next_stages_come_from_the_core_transition_table(self) -> None:
        """Projected rather than restated in the Workbench: a UI-side copy of
        the transition table stays plausible while being wrong."""
        self.assertEqual(self.agent.gate("PROTOTYPING")["next_stages"], ["PROTOTYPING"])

    def test_an_approved_hypothesis_opens_the_gate(self) -> None:
        self._record_hypothesis()
        result = self.agent.gate("PROTOTYPING")
        self.assertEqual(result["result"], "pass")
        self.assertTrue(
            all(r["status"] == "satisfied" for r in result["requirements"])
        )

    def test_an_unapproved_hypothesis_still_blocks_on_approval(self) -> None:
        """Completing the fields is not enough. This is the requirement that is
        easy to miss, because the two hypothesis checks pass without it."""
        self._record_hypothesis(approved=False)
        statuses = self._statuses()
        self.assertEqual(statuses["HYPOTHESIS_PRESENT"], "satisfied")
        self.assertEqual(statuses["HYPOTHESIS_COMPLETE"], "satisfied")
        self.assertEqual(statuses["HUMAN_APPROVAL"], "missing")

    def test_advancing_through_a_blocked_gate_is_refused(self) -> None:
        with self.assertRaises(Exception) as caught:
            self.agent.advance("PROTOTYPING")
        # The core's refusal carries the gate, so the caller can show why.
        self.assertIn("gate", getattr(caught.exception, "details", {}))

    def test_advancing_a_ready_gate_moves_the_stage(self) -> None:
        self._record_hypothesis()
        result = self.agent.advance("PROTOTYPING")
        self.assertEqual(result["from_stage"], "DISCOVERY")
        self.assertEqual(result["to_stage"], "PROTOTYPING")
        self.assertEqual(self.agent.project_status()["stage"], "PROTOTYPING")
        # The branch after prototyping is a real fork, and both arms are legal.
        self.assertEqual(
            self.agent.gate("PLAYTEST_REQUIRED")["next_stages"],
            ["PLAYTEST_REQUIRED", "PROTOTYPE_DECISION"],
        )

    def test_a_lowercase_stage_is_accepted(self) -> None:
        """The core works in uppercase; a caller should not have to know."""
        self._record_hypothesis()
        self.assertEqual(self.agent.advance("prototyping")["to_stage"], "PROTOTYPING")

    def test_an_unknown_transition_is_reported_not_attempted(self) -> None:
        result = self.agent.gate("VERTICAL_SLICE")
        self.assertEqual(result["result"], "blocked")
        self.assertIn("TRANSITION_ALLOWED", self._statuses("VERTICAL_SLICE"))

    def _reach_prototyping_with_scope_evidence(self) -> None:
        self._record_hypothesis()
        self.agent.advance("PROTOTYPING", **APPROVAL)
        note = self.root / "scope.md"
        note.write_text("Needs netcode the project cannot fund.")
        self.agent.project.add_evidence(
            "technical", note, "human_attested", "observation", None, "operator-note"
        )

    def test_the_early_gate_tests_its_arguments_not_the_record(self) -> None:
        """The reason and approver are checked as supplied, which is why the
        gate has to be answerable with them. Checking without them reports
        requirements that the advance would immediately satisfy."""
        self._reach_prototyping_with_scope_evidence()

        bare = {r["code"]: r["status"] for r in self.agent.gate("PROTOTYPE_DECISION")["requirements"]}
        self.assertEqual(bare["EARLY_DECISION_REASON"], "missing")
        self.assertEqual(bare["HUMAN_APPROVAL"], "missing")
        self.assertEqual(bare["EARLY_DECISION_EVIDENCE"], "satisfied")

        answered = self.agent.gate("PROTOTYPE_DECISION", reason="scope", **APPROVAL)
        self.assertEqual(answered["result"], "pass")
        self.assertTrue(all(r["status"] == "satisfied" for r in answered["requirements"]))

    def test_an_early_decision_advances_with_its_reason(self) -> None:
        self._reach_prototyping_with_scope_evidence()
        result = self.agent.advance("PROTOTYPE_DECISION", reason="scope", **APPROVAL)
        self.assertEqual(result["to_stage"], "PROTOTYPE_DECISION")
        self.assertEqual(self.agent.project_status()["stage"], "PROTOTYPE_DECISION")

    def test_an_early_decision_without_a_reason_is_refused(self) -> None:
        self._reach_prototyping_with_scope_evidence()
        with self.assertRaises(Exception) as caught:
            self.agent.advance("PROTOTYPE_DECISION", **APPROVAL)
        self.assertIn("gate", getattr(caught.exception, "details", {}))

    def test_an_unsupported_reason_is_refused_before_the_core(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.advance("PROTOTYPE_DECISION", reason="because")
        self.assertEqual(caught.exception.code, "TRANSITION_REASON_INVALID")


if __name__ == "__main__":
    unittest.main()
