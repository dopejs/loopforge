"""Diagnosis and recovery.

ADR 0003 makes interrupted writes and stale snapshots normal conditions rather
than emergencies. What matters here is that the Workbench can say what is wrong
and get out of it, because a stale snapshot blocks every gate.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject
from loopforge_agent.application import LoopforgeAgent

APPROVAL = {
    "approver_id": "op_local",
    "approver_name": "Local Operator",
    "rationale": "Signals are observable.",
}


class ProjectFixture(unittest.TestCase):
    """Shared setup only. Subclassing a test class would re-run its cases."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _stale_snapshot(self) -> None:
        """Rewind the derived snapshot so it no longer matches the log.

        This is the shape of an interrupted write: the event was committed and
        the snapshot replacement did not finish.
        """
        path = self.root / ".loopforge" / "state.json"
        state = json.loads(path.read_text())
        state["revision"] = state["revision"] - 1
        path.write_text(json.dumps(state))


class HealthTests(ProjectFixture):
    def test_an_uninitialized_project_answers_rather_than_raising(self) -> None:
        result = self.agent.project_health()
        self.assertFalse(result["initialized"])
        self.assertFalse(result["needs_reconcile"])

    def test_a_healthy_project_reports_no_reconcile(self) -> None:
        self.agent.project.init()
        result = self.agent.project_health()
        self.assertTrue(result["initialized"])
        self.assertEqual(result["snapshot_status"], "current")
        self.assertFalse(result["needs_reconcile"])

    def test_a_stale_snapshot_is_reported_as_its_own_condition(self) -> None:
        """Not just one diagnostic among several: it is the one that blocks
        every gate and the one the user can fix from the Workbench."""
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
        self._stale_snapshot()

        result = self.agent.project_health()

        self.assertTrue(result["needs_reconcile"])
        self.assertFalse(result["valid"])
        self.assertIn(
            "STATE_SNAPSHOT_NOT_CURRENT", {item["code"] for item in result["diagnostics"]}
        )

    def test_a_stale_snapshot_blocks_the_gate_it_is_reported_beside(self) -> None:
        """The reason this matters. Without reconcile the project cannot
        advance, whatever else is satisfied."""
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
        self.assertEqual(self.agent.gate("PROTOTYPING")["result"], "pass")

        self._stale_snapshot()

        gate = self.agent.gate("PROTOTYPING")
        self.assertEqual(gate["result"], "blocked")
        self.assertIn(
            "STATE_SNAPSHOT_CURRENT", {item["code"] for item in gate["requirements"]}
        )

    def test_a_condition_reported_twice_is_listed_once(self) -> None:
        """validate and doctor both notice a stale snapshot. A surface keyed on
        the code would render two identical rows."""
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
        self._stale_snapshot()

        codes = [item["code"] for item in self.agent.project_health()["diagnostics"]]

        self.assertEqual(len(codes), len(set(codes)), codes)
        self.assertIn("STATE_SNAPSHOT_NOT_CURRENT", codes)

    def test_a_missing_engine_is_reported_without_hiding_state_integrity(self) -> None:
        """Doctor raises when no Godot is present. That must not swallow the
        validation answer the caller also asked for."""
        self.agent.project.init()
        (self.root / "project.godot").write_text('[application]\nconfig/name="X"\n')

        result = self.agent.project_health()

        self.assertTrue(result["initialized"])
        self.assertEqual(result["snapshot_status"], "current")


class ReconcileTests(ProjectFixture):
    def test_a_dry_run_reports_the_work_without_doing_it(self) -> None:
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
        self._stale_snapshot()

        preview = self.agent.reconcile(apply=False)

        self.assertFalse(preview["applied"])
        self.assertEqual(
            [item["action"] for item in preview["actions"]], ["rebuild_state_snapshot"]
        )
        # Still stale: a preview that changed things would not be a preview.
        self.assertTrue(self.agent.project_health()["needs_reconcile"])

    def test_applying_it_restores_the_snapshot(self) -> None:
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
        self._stale_snapshot()

        result = self.agent.reconcile(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["snapshot_status"], "current")
        health = self.agent.project_health()
        self.assertFalse(health["needs_reconcile"])
        self.assertTrue(health["valid"])
        # And the gate it was blocking opens again.
        self.assertEqual(self.agent.gate("PROTOTYPING")["result"], "pass")

    def test_a_healthy_project_has_nothing_to_reconcile(self) -> None:
        self.agent.project.init()
        self.assertEqual(self.agent.reconcile(apply=False)["actions"], [])


class HistoryTests(ProjectFixture):
    def test_an_uninitialized_project_has_an_empty_trail(self) -> None:
        result = self.agent.history()
        self.assertEqual(result["events"], [])
        self.assertFalse(result["truncated"])

    def test_events_are_summarised_newest_first(self) -> None:
        """Payloads carry whole run records and hypothesis documents; the audit
        view needs what happened, not a second copy of the artifacts."""
        self.agent.project.init()
        self.agent.create_hypothesis(
            {key: f"value {key}" for key in HYPOTHESIS_FIELDS}, **APPROVAL
        )
        self.agent.advance("PROTOTYPING", **APPROVAL)

        events = self.agent.history()["events"]

        self.assertEqual(events[0]["event_type"], "stage.transitioned")
        self.assertEqual(events[0]["detail"], "DISCOVERY → PROTOTYPING")
        self.assertEqual(events[1]["event_type"], "hypothesis.created")
        self.assertEqual(events[1]["detail"], "revision 1")
        # Revisions descend, and no payload rides along.
        self.assertGreater(events[0]["revision"], events[-1]["revision"])
        self.assertNotIn("payload", events[0])


if __name__ == "__main__":
    unittest.main()
