"""Playtest protocol and report handling.

The report is where the product's honesty rules become code: consent is a
statement about a real person and is never defaulted, and raw observations are
kept separate from the interpretation drawn from them (ADR 0002).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from loopforge.project import (
    HYPOTHESIS_FIELDS,
    PLAYTEST_LIST_FIELDS,
    PLAYTEST_REPORT_FIELDS,
    LoopforgeProject,
)
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
        "build_identity": "sha256:test-build",
        "participant_context": "One player, no prior exposure to the build.",
        "consent_status": "obtained",
        "assistance_given": "None.",
        "raw_observations": [
            "Charged near the hazard twice",
            "Died on the third attempt",
        ],
        "comprehension_time": "About 40 seconds to understand charging.",
        "confusion_points": ["Unclear that charging could be cancelled"],
        "failure_points": [],
        "abandonment_points": [],
        "strategies": ["Waited for the hazard to pass before charging"],
        "replay_behavior": "Restarted twice without prompting.",
        "interpretation": "The risk trade-off reads, but cancelling is undiscoverable.",
        "sensitive_data": "No identifying data; anonymous notes deleted after review.",
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

        result = self.agent.create_playtest_protocol(
            "# Protocol\n\nWatch, do not prompt."
        )

        self.assertIsNotNone(result["protocol"])
        self.assertTrue(result["protocol"]["protocol_id"])
        self.assertTrue(result["protocol"]["build_identity"].startswith("sha256:"))
        self.assertEqual(result["build_identity"], result["protocol"]["build_identity"])
        schema = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "contracts/loopforge-playtest-protocol-v1.schema.json"
            ).read_text()
        )
        stored = self.agent.project._latest_protocol(
            self.agent.project.store.current_state()[0]
        )
        self.assertIsNotNone(stored)
        self.assertLessEqual(set(schema["required"]), set(stored))
        self.assertLessEqual(set(stored), set(schema["properties"]))

    def test_an_empty_protocol_is_refused(self) -> None:
        self._reach_playtest_stage()
        for value in ("", "   \n  "):
            with (
                self.subTest(value=value),
                self.assertRaises(LoopforgeAgentError) as caught,
            ):
                self.agent.create_playtest_protocol(value)
            self.assertEqual(caught.exception.code, "PLAYTEST_PROTOCOL_INVALID")

    def test_the_core_also_refuses_an_empty_protocol(self) -> None:
        self._reach_playtest_stage()
        empty = self.root / "empty-protocol.md"
        empty.write_text("  \n")

        with self.assertRaises(Exception) as caught:
            self.agent.project.create_playtest_protocol(empty, expected_revision=None)

        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""),
            "PLAYTEST_PROTOCOL_INVALID",
        )

    def test_a_report_satisfies_the_human_playtested_claim(self) -> None:
        self._reach_playtest_stage()
        self.agent.create_playtest_protocol("# Protocol\n\nWatch, do not prompt.")

        self.agent.import_playtest_report(
            report(build_identity=self.agent.playtest()["build_identity"])
        )

        claims = {
            c["claim"]: c["status"] for c in self.agent.project_status()["claims"]
        }
        self.assertEqual(claims["HUMAN_PLAYTESTED"], "satisfied")
        # Orthogonal: a person playing it says nothing about whether it builds.
        self.assertEqual(claims["FUN_HYPOTHESIS_SUPPORTED"], "unknown")

    def test_decision_gate_requires_a_person_to_confirm_the_report(self) -> None:
        self._reach_playtest_stage()
        protocol = self.agent.create_playtest_protocol("# Protocol\n\nWatch.")
        self.agent.import_playtest_report(
            report(build_identity=protocol["build_identity"])
        )

        self.assertEqual(
            self.agent.project.gate_check("PROTOTYPE_DECISION")["result"],
            "blocked",
        )
        self.assertEqual(
            self.agent.project.gate_check("PROTOTYPE_DECISION", **APPROVAL)["result"],
            "pass",
        )

    def test_a_report_without_a_protocol_is_refused(self) -> None:
        """The protocol is what the observations were gathered against; a
        report without one cannot be scoped to anything."""
        self._reach_playtest_stage()
        with self.assertRaises(Exception) as caught:
            self.agent.import_playtest_report(
                report(build_identity=self.agent.playtest()["build_identity"])
            )
        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""),
            "PLAYTEST_PROTOCOL_MISSING",
        )

    def test_a_report_must_match_the_build_bound_to_the_protocol(self) -> None:
        self._reach_playtest_stage()
        state = self.agent.create_playtest_protocol("# Protocol\n\nWatch.")

        with self.assertRaises(Exception) as caught:
            self.agent.import_playtest_report(report(build_identity="sha256:wrong"))

        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""),
            "PLAYTEST_BUILD_MISMATCH",
        )
        self.assertTrue(state["build_identity"].startswith("sha256:"))

    def test_source_changes_after_the_protocol_refuse_the_report(self) -> None:
        self._reach_playtest_stage()
        state = self.agent.create_playtest_protocol("# Protocol\n\nWatch.")
        (self.root / "changed.gd").write_text("extends Node\n")

        with self.assertRaises(Exception) as caught:
            self.agent.import_playtest_report(
                report(build_identity=state["build_identity"])
            )

        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""),
            "PLAYTEST_BUILD_STALE",
        )

    def test_consent_revocation_removes_report_and_invalidates_claim(self) -> None:
        self._reach_playtest_stage()
        state = self.agent.create_playtest_protocol("# Protocol\n\nWatch.")
        imported = self.agent.import_playtest_report(
            report(build_identity=state["build_identity"])
        )
        evidence_id = imported["report"]["evidence_id"]
        record = self.agent.project._evidence_by_id()[evidence_id]
        artifact = self.root / record["artifact"]["path"]
        self.assertTrue(artifact.is_file())

        revoked = self.agent.revoke_playtest_report(
            evidence_id,
            "The participant withdrew consent after the session.",
        )

        self.assertTrue(revoked["report"]["revoked"])
        self.assertFalse(artifact.exists())
        listed = self.agent.project._evidence_by_id()[evidence_id]
        self.assertTrue(listed["revoked"])
        self.assertEqual(
            listed["revocation_reason"],
            "The participant withdrew consent after the session.",
        )
        self.assertEqual(
            self.agent.project.history()["events"][-1]["event_type"],
            "evidence.revoked",
        )
        claims = {
            c["claim"]: c["status"] for c in self.agent.project_status()["claims"]
        }
        self.assertEqual(claims["HUMAN_PLAYTESTED"], "unknown")
        self.assertEqual(self.agent.decision()["playtest_evidence_ids"], [])
        self.assertEqual(
            self.agent.project.gate_check("PROTOTYPE_DECISION", **APPROVAL)["result"],
            "blocked",
        )
        self.assertTrue(self.agent.project.validate()["valid"])

    def test_consent_revocation_is_idempotent(self) -> None:
        self._reach_playtest_stage()
        state = self.agent.create_playtest_protocol("# Protocol\n\nWatch.")
        imported = self.agent.import_playtest_report(
            report(build_identity=state["build_identity"])
        )
        evidence_id = imported["report"]["evidence_id"]
        first = self.agent.project.revoke_playtest_evidence(
            evidence_id, "Consent withdrawn.", expected_revision=None
        )
        second = self.agent.project.revoke_playtest_evidence(
            evidence_id, "Consent withdrawn.", expected_revision=None
        )

        self.assertFalse(first["already_revoked"])
        self.assertTrue(second["already_revoked"])
        self.assertEqual(first["committed_revision"], second["committed_revision"])

    def test_revocation_retries_report_deletion_after_an_io_failure(self) -> None:
        self._reach_playtest_stage()
        state = self.agent.create_playtest_protocol("# Protocol\n\nWatch.")
        imported = self.agent.import_playtest_report(
            report(build_identity=state["build_identity"])
        )
        evidence_id = imported["report"]["evidence_id"]
        stored = self.root / self.agent.project._evidence_by_id()[evidence_id][
            "artifact"
        ]["path"]

        with patch.object(Path, "unlink", side_effect=PermissionError("locked")):
            first = self.agent.project.revoke_playtest_evidence(
                evidence_id, "Consent withdrawn.", expected_revision=None
            )

        self.assertTrue(stored.is_file())
        self.assertFalse(first["artifact_deleted"])
        self.assertIn("locked", first["deletion_error"])
        self.assertEqual(
            self.agent.project.status()["claims"]["HUMAN_PLAYTESTED"]["status"],
            "unknown",
        )

        retried = self.agent.project.revoke_playtest_evidence(
            evidence_id, "Consent withdrawn.", expected_revision=None
        )
        self.assertTrue(retried["already_revoked"])
        self.assertTrue(retried["artifact_deleted"])
        self.assertFalse(stored.exists())
        self.assertEqual(first["committed_revision"], retried["committed_revision"])

    def test_playtest_projection_and_report_vocabulary_match_contracts(self) -> None:
        root = Path(__file__).resolve().parents[2]
        state_schema = json.loads(
            (root / "contracts" / "loopforge-playtest-v1.schema.json").read_text()
        )
        report_schema = json.loads(
            (
                root / "contracts" / "loopforge-playtest-report-v1.schema.json"
            ).read_text()
        )
        state = self.agent.playtest()

        self.assertEqual(set(state), set(state_schema["required"]))
        self.assertEqual(set(PLAYTEST_REPORT_FIELDS), set(report_schema["required"]))
        self.assertEqual(set(PLAYTEST_REPORT_FIELDS), set(report_schema["properties"]))
        self.assertEqual(set(state["fields"]), set(PLAYTEST_REPORT_FIELDS))
        self.assertEqual(set(state["list_fields"]), set(PLAYTEST_LIST_FIELDS))


class PlaytestReportValidationTests(unittest.TestCase):
    """Validation that does not need a project, exercised directly."""

    def _clean(self, value: object) -> dict:
        return LoopforgeAgent._clean_playtest_report(value)

    def test_consent_is_never_defaulted(self) -> None:
        """The central rule. An unanswered consent question must fail rather
        than resolve to not_required, which is itself a claim about a person.
        """
        for value in (None, "", "unknown", "yes", True):
            with (
                self.subTest(value=value),
                self.assertRaises(LoopforgeAgentError) as caught,
            ):
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
            with (
                self.subTest(value=value),
                self.assertRaises(LoopforgeAgentError) as caught,
            ):
                self._clean(report(raw_observations=value))
            self.assertEqual(caught.exception.code, "PLAYTEST_REPORT_INVALID")

    def test_blank_list_entries_are_refused_not_silently_dropped(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self._clean(report(confusion_points=["  ", "Real point", ""]))
        self.assertEqual(caught.exception.code, "PLAYTEST_REPORT_INVALID")

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
            with (
                self.subTest(field=field),
                self.assertRaises(LoopforgeAgentError) as caught,
            ):
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
            self._clean(
                report(raw_observations=[f"observation {n}" for n in range(201)])
            )
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
