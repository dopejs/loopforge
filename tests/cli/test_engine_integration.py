"""Engine adapter tests against a real Godot binary.

`run_engine` had no test coverage of any kind while already being reachable
from a button in the Workbench. These tests execute it: a real engine boots the
fixture scene, the adapter reads a real exit code, and the derived quality
claim is asserted from the resulting evidence.

The claim assertions are the point. A build alone or a test alone leaves
TECHNICALLY_VALIDATED unknown; only both together satisfy it. That is what the
Workbench's run controls have to produce, and it cannot be verified with a stub
that never boots an engine.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from loopforge.errors import InvalidStateError
from loopforge.project import LoopforgeProject
from tests.support.godot import EXIT_CODE_VARIABLE, materialize_fixture, requires_godot


def claim_status(project: LoopforgeProject, name: str) -> str:
    return project.status()["claims"][name]["status"]


@requires_godot
class EngineAdapterIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = materialize_fixture()
        self.project = LoopforgeProject(self.root)
        self.project.init()

    def tearDown(self) -> None:
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def test_a_build_produces_tool_generated_evidence(self) -> None:
        result = self.project.run_engine("build", expected_revision=None)

        self.assertEqual(result["run"]["status"], "completed")
        self.assertEqual(result["run"]["exit_code"], 0)
        self.assertEqual(result["run"]["adapter"], "godot")
        # Parsed from the real binary's --version output rather than a fixed
        # string, so a change in that format fails here instead of silently
        # recording an empty adapter version in evidence.
        self.assertTrue(result["run"]["adapter_version"].startswith("4."))

        evidence = result["evidence"]
        self.assertEqual(evidence["type"], "build")
        self.assertEqual(evidence["result"], "passed")
        self.assertEqual(evidence["trust_level"], "tool_generated")

    def test_a_claim_needs_both_a_build_and_a_test(self) -> None:
        """The assertion behind R4: one run is never enough."""
        self.assertEqual(claim_status(self.project, "TECHNICALLY_VALIDATED"), "unknown")

        self.project.run_engine("test", expected_revision=None)
        self.assertEqual(
            claim_status(self.project, "TECHNICALLY_VALIDATED"),
            "unknown",
            "a test alone must not satisfy the claim",
        )

        self.project.run_engine("build", expected_revision=None)
        self.assertEqual(claim_status(self.project, "TECHNICALLY_VALIDATED"), "satisfied")

    def test_a_failing_scene_is_recorded_as_failed(self) -> None:
        """A non-zero exit from the engine must become failed evidence.

        Driven by booting a scene that really quits with code 3, so the path
        from process exit code to claim status is executed end to end.
        """
        self.project.run_engine("build", expected_revision=None)

        with patch.dict("os.environ", {EXIT_CODE_VARIABLE: "3"}):
            result = self.project.run_engine("test", expected_revision=None)

        self.assertEqual(result["run"]["status"], "failed")
        self.assertEqual(result["run"]["exit_code"], 3)
        self.assertEqual(result["evidence"]["result"], "failed")
        self.assertEqual(claim_status(self.project, "TECHNICALLY_VALIDATED"), "failed")

    def test_doctor_accepts_the_fixture_against_a_real_engine(self) -> None:
        """Version detection and main-scene resolution against a real install.

        Both checks parse real artifacts -- the binary's version output and
        project.godot -- so a stub can confirm the code path but not the
        contract.
        """
        checks = {item["code"]: item for item in self.project.doctor()["checks"]}
        self.assertEqual(checks["GODOT_VERSION"]["status"], "passed")
        self.assertEqual(checks["GODOT_MAIN_SCENE"]["status"], "passed")
        # The version came out of the binary, not out of a constant.
        self.assertTrue(checks["GODOT_VERSION"]["details"]["version"].startswith("4."))
        # GODOT_EXECUTABLE is only emitted on the missing-binary path, so its
        # absence here is the check passing rather than a check being skipped.
        self.assertNotIn("GODOT_EXECUTABLE", checks)

    def test_a_project_without_godot_config_is_refused(self) -> None:
        (self.root / "project.godot").unlink()
        with self.assertRaises(InvalidStateError) as caught:
            self.project.run_engine("test", expected_revision=None)
        self.assertEqual(caught.exception.diagnostic_code, "ENGINE_PROJECT_NOT_DETECTED")


if __name__ == "__main__":
    unittest.main()
