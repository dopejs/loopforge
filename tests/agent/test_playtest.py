"""Playtest protocol and report handling.

The report is where the product's honesty rules become code: consent is a
statement about a real person and is never defaulted, and raw observations are
kept separate from the interpretation drawn from them (ADR 0002).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError

APPROVAL = {
    "approver_id": "op_local",
    "approver_name": "Local Operator",
    "rationale": "Signals are observable.",
}

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def report(**overrides: object) -> dict:
    base = {
        "participant_context": "One player, no prior exposure to the build.",
        "consent_status": "obtained",
        "raw_observations": ["Charged near the hazard twice", "Died on the third attempt"],
        "comprehension_time": "About 40 seconds to understand charging.",
        "confusion_points": ["Unclear that charging could be cancelled"],
        "failure_points": [],
        "abandonment_points": [],
        "strategies": ["Waited for the hazard to pass before charging"],
        "replay_behavior": "Restarted twice without prompting.",
        "interpretation": "The risk trade-off reads, but cancelling is undiscoverable.",
    }
    base.update(overrides)
    return base


class PlaytestStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _reach_playtest_stage(self) -> None:
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
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
        self.agent.advance("PLAYTEST_REQUIRED", **APPROVAL)

    def test_an_uninitialized_project_reports_state_rather_than_failing(self) -> None:
        result = self.agent.playtest()
        self.assertFalse(result["allowed"])
        self.assertIsNone(result["protocol"])
        # The surface needs the vocabulary before anything exists, to render a
        # consent control that has no default.
        self.assertEqual(result["consent_values"], ["obtained", "not_required"])

    def test_the_stage_requirement_is_reported_not_raised(self) -> None:
        """A user in discovery should read why, not a PLAYTEST_STAGE_INVALID
        code from three layers down."""
        self.agent.project.init()
        result = self.agent.playtest()
        self.assertEqual(result["stage"], "DISCOVERY")
        self.assertFalse(result["allowed"])

    def test_a_protocol_is_recorded_and_then_visible(self) -> None:
        self._reach_playtest_stage()
        self.assertTrue(self.agent.playtest()["allowed"])
        self.assertIsNone(self.agent.playtest()["protocol"])

        result = self.agent.create_playtest_protocol("# Protocol\n\nWatch, do not prompt.")

        self.assertIsNotNone(result["protocol"])
        self.assertTrue(result["protocol"]["protocol_id"])

    def test_an_empty_protocol_is_refused(self) -> None:
        self._reach_playtest_stage()
        for value in ("", "   \n  "):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.create_playtest_protocol(value)
            self.assertEqual(caught.exception.code, "PLAYTEST_PROTOCOL_INVALID")

    def test_a_report_satisfies_the_human_playtested_claim(self) -> None:
        self._reach_playtest_stage()
        self.agent.create_playtest_protocol("# Protocol\n\nWatch, do not prompt.")

        self.agent.import_playtest_report(report())

        claims = {c["claim"]: c["status"] for c in self.agent.project_status()["claims"]}
        self.assertEqual(claims["HUMAN_PLAYTESTED"], "satisfied")
        # Orthogonal: a person playing it says nothing about whether it builds.
        self.assertEqual(claims["FUN_HYPOTHESIS_SUPPORTED"], "unknown")

    def test_a_report_without_a_protocol_is_refused(self) -> None:
        """The protocol is what the observations were gathered against; a
        report without one cannot be scoped to anything."""
        self._reach_playtest_stage()
        with self.assertRaises(Exception) as caught:
            self.agent.import_playtest_report(report())
        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""), "PLAYTEST_PROTOCOL_MISSING"
        )


class PlaytestReportValidationTests(unittest.TestCase):
    """Validation that does not need a project, exercised directly."""

    def _clean(self, value: object) -> dict:
        return LoopforgeAgent._clean_playtest_report(value)

    def test_consent_is_never_defaulted(self) -> None:
        """The central rule. An unanswered consent question must fail rather
        than resolve to not_required, which is itself a claim about a person.
        """
        for value in (None, "", "unknown", "yes", True):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self._clean(report(consent_status=value))
            self.assertEqual(caught.exception.code, "PLAYTEST_CONSENT_INVALID")

    def test_both_consent_answers_are_accepted(self) -> None:
        for value in ("obtained", "not_required"):
            with self.subTest(value=value):
                self.assertEqual(
                    self._clean(report(consent_status=value))["consent_status"], value
                )

    def test_an_empty_interpretation_is_refused(self) -> None:
        """Observations without a reading are incomplete, and a reading is not
        allowed to be implied from them."""
        with self.assertRaises(LoopforgeAgentError):
            self._clean(report(interpretation="   "))

    def test_raw_observations_must_contain_something(self) -> None:
        for value in ([], ["", "  "]):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self._clean(report(raw_observations=value))
            self.assertEqual(caught.exception.code, "PLAYTEST_REPORT_INVALID")

    def test_blank_list_entries_are_dropped_not_stored(self) -> None:
        cleaned = self._clean(report(confusion_points=["  ", "Real point", ""]))
        self.assertEqual(cleaned["confusion_points"], ["Real point"])

    def test_optional_lists_may_be_empty(self) -> None:
        cleaned = self._clean(report(failure_points=[], strategies=[]))
        self.assertEqual(cleaned["failure_points"], [])

    def test_a_non_list_field_is_refused(self) -> None:
        with self.assertRaises(LoopforgeAgentError):
            self._clean(report(strategies="waited"))

    def test_unknown_fields_are_refused(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self._clean(report(mood="cheerful"))
        self.assertIn("mood", str(caught.exception))

    def test_oversized_text_is_refused_rather_than_truncated(self) -> None:
        """These land in an append-only log. Silently dropping a tail would
        alter the record without saying so."""
        long = "x" * 4_001
        for field in (
            "participant_context",
            "comprehension_time",
            "replay_behavior",
            "interpretation",
        ):
            with self.subTest(field=field), self.assertRaises(LoopforgeAgentError) as caught:
                self._clean(report(**{field: long}))
            self.assertEqual(caught.exception.code, "PLAYTEST_REPORT_INVALID")

    def test_an_oversized_list_entry_is_refused(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self._clean(report(raw_observations=["fine", "y" * 4_001]))
        self.assertEqual(caught.exception.code, "PLAYTEST_REPORT_INVALID")

    def test_too_many_entries_are_refused_rather_than_dropped(self) -> None:
        """Previously the list was sliced, so entries past the cap vanished
        while the import reported success."""
        with self.assertRaises(LoopforgeAgentError) as caught:
            self._clean(report(raw_observations=[f"observation {n}" for n in range(201)]))
        self.assertEqual(caught.exception.code, "PLAYTEST_REPORT_INVALID")

    def test_interpretation_stays_out_of_the_observations(self) -> None:
        """Separation is structural, not stylistic: the two travel as distinct
        fields so a later reader can tell what was seen from what was
        concluded."""
        cleaned = self._clean(report())
        self.assertIsInstance(cleaned["raw_observations"], list)
        self.assertIsInstance(cleaned["interpretation"], str)
        self.assertNotIn(cleaned["interpretation"], cleaned["raw_observations"])


if __name__ == "__main__":
    unittest.main()
