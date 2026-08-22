"""The prototype decision: the product's terminal act.

Everything here exists to stop a decision from being recorded as more than it
is -- without an author, without cited evidence, or as a `keep` that the
playtest never supported.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError
from tests.agent.test_evidence import PNG
from tests.agent.test_playtest import report

APPROVAL = {
    "approver_id": "op_local",
    "approver_name": "Local Operator",
    "rationale": "Signals are observable.",
}


def fields(prefix: str = "value") -> dict[str, str]:
    return {key: f"{prefix} {key}" for key in HYPOTHESIS_FIELDS}


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _reach_decision(self, with_playtest: bool = True) -> None:
        self.agent.project.init()
        self.agent.create_hypothesis(fields(), **APPROVAL)
        self.agent.advance("PROTOTYPING", **APPROVAL)
        for kind in ("build", "test"):
            path = self.root / f"{kind}.json"
            path.write_text("{}")
            self.agent.project.add_evidence(
                kind, path, "manually_imported", "passed", None, "test-fixture"
            )
        shot = self.root / "shot.png"
        shot.write_bytes(PNG)
        self.agent.register_capture(str(shot))
        if with_playtest:
            self.agent.advance("PLAYTEST_REQUIRED", **APPROVAL)
            self.agent.create_playtest_protocol("# Protocol\n\nWatch.")
            self.agent.import_playtest_report(report())
            self.agent.advance("PROTOTYPE_DECISION", **APPROVAL)
        else:
            # The early path: prototyping straight to a decision. It needs its
            # own evidence -- a passing build says nothing about why the
            # experiment is being cut short, so the gate wants a technical,
            # scope or abandonment record, or a failed run.
            note = self.root / "scope.md"
            note.write_text("The mechanic needs netcode the project cannot fund.")
            self.agent.project.add_evidence(
                "technical", note, "human_attested", "observation", None, "operator-note"
            )
            self.agent.advance("PROTOTYPE_DECISION", reason="scope", **APPROVAL)

    def _evidence_ids(self, kind: str | None = None) -> list[str]:
        return [
            item["id"]
            for item in self.agent.evidence()["evidence"]
            if kind is None or item["type"] == kind
        ]

    def test_the_three_outcomes_are_offered_as_equals(self) -> None:
        """Order and completeness come from the core. A surface that promoted
        `keep` would bias the judgement the product exists to make."""
        self.assertEqual(self.agent.decision()["decisions"], ["keep", "kill", "refactor"])

    def test_state_reports_the_stage_rather_than_failing(self) -> None:
        self.agent.project.init()
        state = self.agent.decision()
        self.assertEqual(state["stage"], "DISCOVERY")
        self.assertFalse(state["allowed"])
        self.assertIsNone(state["recorded"])

    def test_a_keep_supports_the_fun_claim_once_the_playtest_is_cited(self) -> None:
        self._reach_decision()
        self.assertTrue(self.agent.decision()["allowed"])

        result = self.agent.decide("keep", self._evidence_ids(), rationale="It reads.", **{
            "approver_id": "op_local",
            "approver_name": "Local Operator",
        })

        self.assertEqual(result["decision"], "keep")
        self.assertEqual(result["stage"], "VERTICAL_SLICE")
        claims = {c["claim"]: c["status"] for c in self.agent.project_status()["claims"]}
        self.assertEqual(claims["FUN_HYPOTHESIS_SUPPORTED"], "satisfied")

    def test_a_keep_that_does_not_cite_the_playtest_is_refused(self) -> None:
        """The core requires the report to be cited, not merely to exist. A
        keep resting on a build alone would claim human support it never had.
        """
        self._reach_decision()
        technical = [
            item["id"]
            for item in self.agent.evidence()["evidence"]
            if item["type"] in {"build", "test"}
        ]

        with self.assertRaises(Exception) as caught:
            self.agent.decide(
                "keep", technical, "op_local", "Local Operator", "It reads."
            )

        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""),
            "DECISION_PLAYTEST_NOT_CITED",
        )

    def test_a_kill_records_a_failed_claim_rather_than_an_unknown_one(self) -> None:
        self._reach_decision(with_playtest=False)
        result = self.agent.decide(
            "kill", self._evidence_ids(), "op_local", "Local Operator", "Out of scope."
        )
        self.assertEqual(result["stage"], "KILLED")
        claims = {c["claim"]: c["status"] for c in self.agent.project_status()["claims"]}
        self.assertEqual(claims["FUN_HYPOTHESIS_SUPPORTED"], "failed")

    def test_a_refactor_returns_to_prototyping_with_a_new_hypothesis(self) -> None:
        self._reach_decision()
        result = self.agent.decide(
            "refactor",
            self._evidence_ids(),
            "op_local",
            "Local Operator",
            "Charging is undiscoverable; retest with a visible meter.",
            revised_fields=fields("revised"),
        )
        self.assertEqual(result["stage"], "PROTOTYPING")
        current = self.agent.hypothesis()
        self.assertEqual(current["fields"]["hypothesis"], "revised hypothesis")
        self.assertEqual(current["revision"], 2)

    def test_a_refactor_without_a_revised_hypothesis_is_refused(self) -> None:
        self._reach_decision()
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.decide(
                "refactor", self._evidence_ids(), "op_local", "Local Operator", "Retest."
            )
        self.assertEqual(caught.exception.code, "HYPOTHESIS_INCOMPLETE")

    def test_a_decision_without_evidence_is_refused(self) -> None:
        self._reach_decision()
        for value in ([], None, "evd_1", ["", "  "]):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.decide("kill", value, "op_local", "Local Operator", "No.")
            self.assertEqual(caught.exception.code, "DECISION_EVIDENCE_MISSING")

    def test_a_decision_without_a_rationale_is_refused(self) -> None:
        """Whitespace is not a reason. This is the sentence a reader months
        later has to weigh the decision by."""
        self._reach_decision()
        for value in ("", "   \n "):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.decide("kill", self._evidence_ids(), "op_local", "Op", value)
            self.assertEqual(caught.exception.code, "DECISION_RATIONALE_MISSING")

    def test_a_decision_without_an_approver_is_refused(self) -> None:
        self._reach_decision()
        for approver_id, approver_name in (("", "Op"), ("op_1", ""), (None, None)):
            with self.subTest(approver_id=approver_id), self.assertRaises(
                LoopforgeAgentError
            ) as caught:
                self.agent.decide(
                    "kill", self._evidence_ids(), approver_id, approver_name, "No."
                )
            self.assertEqual(caught.exception.code, "DECISION_APPROVER_MISSING")

    def test_an_unknown_outcome_is_refused(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.decide("maybe", ["evd_1"], "op_1", "Op", "Hmm.")
        self.assertEqual(caught.exception.code, "DECISION_INVALID")

    def test_a_recorded_decision_is_readable_afterwards(self) -> None:
        self._reach_decision()
        self.agent.decide(
            "keep", self._evidence_ids(), "op_local", "Local Operator", "It reads."
        )
        recorded = self.agent.decision()["recorded"]
        self.assertEqual(recorded["decision"], "keep")


if __name__ == "__main__":
    unittest.main()
