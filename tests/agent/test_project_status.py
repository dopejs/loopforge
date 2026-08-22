"""Project status projection: lifecycle stage and quality claims."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from loopforge.errors import InvalidStateError
from loopforge_agent.application import LoopforgeAgent


def agent_with_project(project: object) -> LoopforgeAgent:
    agent = object.__new__(LoopforgeAgent)
    agent.project = project
    return agent


class ProjectStatusTests(unittest.TestCase):
    def test_an_uninitialized_project_is_a_state_not_an_error(self) -> None:
        project = Mock()
        project.status.return_value = {"initialized": False}
        result = agent_with_project(project).project_status()
        self.assertEqual(result["schema_version"], "loopforge-project-status-v1")
        self.assertFalse(result["initialized"])
        self.assertNotIn("claims", result)

    def test_a_core_failure_reports_a_reason_rather_than_raising(self) -> None:
        project = Mock()
        project.status.side_effect = InvalidStateError("not a project", "NOT_A_PROJECT")
        result = agent_with_project(project).project_status()
        self.assertFalse(result["initialized"])
        self.assertIn("not a project", result["reason"])

    def test_claims_are_projected_with_their_evidence_counts(self) -> None:
        project = Mock()
        project.status.return_value = {
            "initialized": True,
            "stage": "PROTOTYPING",
            "observed_revision": 4,
            "evidence_count": 2,
            "snapshot_status": "current",
            "active_experiment": {"experiment_id": "exp_1", "hypothesis_id": None},
            "claims": {
                "TECHNICALLY_VALIDATED": {
                    "status": "satisfied",
                    "evidence_ids": ["ev_1", "ev_2"],
                },
                "HUMAN_PLAYTESTED": {"status": "unknown", "evidence_ids": []},
            },
        }
        result = agent_with_project(project).project_status()

        by_claim = {c["claim"]: c for c in result["claims"]}
        self.assertEqual(by_claim["TECHNICALLY_VALIDATED"]["status"], "satisfied")
        self.assertEqual(by_claim["TECHNICALLY_VALIDATED"]["evidence_count"], 2)
        self.assertEqual(by_claim["HUMAN_PLAYTESTED"]["evidence_count"], 0)
        self.assertEqual(result["stage"], "PROTOTYPING")
        self.assertEqual(result["experiment"]["experiment_id"], "exp_1")

    def test_stale_is_preserved_rather_than_shown_as_satisfied(self) -> None:
        """Evidence that no longer matches the current source is not evidence;
        collapsing stale into satisfied would overstate the project."""
        project = Mock()
        project.status.return_value = {
            "initialized": True,
            "stage": "PROTOTYPING",
            "claims": {"VISUALLY_REVIEWED": {"status": "stale", "evidence_ids": ["ev_9"]}},
        }
        (claim,) = agent_with_project(project).project_status()["claims"]
        self.assertEqual(claim["status"], "stale")

    def test_an_unrecognized_status_becomes_unknown(self) -> None:
        project = Mock()
        project.status.return_value = {
            "initialized": True,
            "claims": {"RELEASE_APPROVED": {"status": "provisional", "evidence_ids": []}},
        }
        (claim,) = agent_with_project(project).project_status()["claims"]
        # A newer core must not be reported as satisfied by accident.
        self.assertEqual(claim["status"], "unknown")

    def test_projection_stays_within_the_contract(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (root / "contracts" / "loopforge-project-status-v1.schema.json").read_text()
        )
        project = Mock()
        project.status.return_value = {
            "initialized": True,
            "stage": "DISCOVERY",
            "observed_revision": 1,
            "evidence_count": 0,
            "snapshot_status": "current",
            "active_experiment": {
                "experiment_id": "exp_1",
                "hypothesis_id": None,
                "hypothesis_revision": None,
                "hypothesis_approval": None,
            },
            "claims": {"TECHNICALLY_VALIDATED": {"status": "unknown", "evidence_ids": []}},
        }
        result = agent_with_project(project).project_status()

        self.assertLessEqual(set(result), set(schema["properties"]))
        allowed_claims = set(schema["properties"]["claims"]["items"]["properties"])
        for claim in result["claims"]:
            self.assertLessEqual(set(claim), allowed_claims)
        self.assertLessEqual(
            set(result["experiment"]), set(schema["properties"]["experiment"]["properties"])
        )


class ProjectStatusOnDiskTests(unittest.TestCase):
    """Against a real initialized project rather than a mock."""

    def test_a_fresh_project_reports_discovery_with_unknown_claims(self) -> None:
        from loopforge.project import LoopforgeProject

        root = Path(tempfile.mkdtemp(prefix="loopforge-status-"))
        project = LoopforgeProject(root)
        project.init()

        result = agent_with_project(project).project_status()
        self.assertTrue(result["initialized"])
        self.assertEqual(result["stage"], "DISCOVERY")
        # A brand-new project has claimed nothing; every claim is unknown.
        self.assertTrue(result["claims"])
        self.assertTrue(all(c["status"] == "unknown" for c in result["claims"]))


if __name__ == "__main__":
    unittest.main()
