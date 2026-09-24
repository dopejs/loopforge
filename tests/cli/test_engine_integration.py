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

import platform
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from loopforge.errors import GateBlockedError, InvalidStateError
from loopforge.project import LoopforgeProject

from tests.support.godot import (
    EXIT_CODE_VARIABLE,
    SELF_TEST_VARIABLE,
    capture_fixture,
    godot_binary,
    materialize_fixture,
    requires_godot,
)


def write_complete_hypothesis(root: Path) -> Path:
    path = root / "hypothesis.md"
    headings = {
        "Intended player": "Players learning a one-button timing game.",
        "Platform": "Desktop keyboard.",
        "Player fantasy": "Risk danger to release a high-value dash.",
        "Core verb": "Charge and release a dash.",
        "Moment to moment loop": "Move, approach danger, charge, dash, score, recover.",
        "Hypothesis": (
            "A first-time player will voluntarily attempt one x3 dash within "
            "two minutes."
        ),
        "Constraints": "One screen, keyboard only, one moving hazard.",
        "Non-goals": "Progression, content, accounts, production art, and audio.",
        "Cheapest validation": (
            "One neutral external session on the single-screen build."
        ),
        "Keep signals": (
            "The participant attempts an x3 dash and restarts without prompting."
        ),
        "Kill signals": (
            "The participant cannot identify charge or risk after two runs."
        ),
    }
    path.write_text(
        "\n\n".join(f"## {heading}\n{value}" for heading, value in headings.items()),
        encoding="utf-8",
    )
    return path


def claim_status(project: LoopforgeProject, name: str) -> str:
    return project.status()["claims"][name]["status"]


APPROVAL = {
    "approver_id": "operator-1",
    "approver_name": "Fixture Operator",
    "rationale": "The evidenced build is ready for external observation.",
}


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

        # The supported workflow imports first, then starts the imported scene.
        # Godot 4.4+ may create source UID sidecars during editor import; running
        # startup first would correctly make that pre-import evidence stale.
        self.project.run_engine("build", expected_revision=None)
        self.assertEqual(
            claim_status(self.project, "TECHNICALLY_VALIDATED"),
            "unknown",
            "a build alone must not satisfy the claim",
        )

        self.project.run_engine("test", expected_revision=None)
        self.assertEqual(
            claim_status(self.project, "TECHNICALLY_VALIDATED"), "satisfied"
        )

    def test_a_missing_run_artifact_cannot_satisfy_the_technical_gate(self) -> None:
        self.project.create_hypothesis(
            write_complete_hypothesis(self.root),
            expected_revision=1,
            approver_id="operator-1",
            approver_name="Fixture Operator",
            rationale="This is the bounded representative experiment.",
        )
        self.project.advance("PROTOTYPING", expected_revision=2)
        self.project.run_engine("build", expected_revision=None)
        self.project.run_engine("test", expected_revision=None)
        result = self.project.run_engine("test", expected_revision=None)
        self.assertEqual(
            claim_status(self.project, "TECHNICALLY_VALIDATED"), "satisfied"
        )
        (self.root / result["evidence"]["artifact"]["path"]).unlink()

        gate = self.project.gate_check(
            "PLAYTEST_REQUIRED",
            approver_id="operator-1",
            approver_name="Fixture Operator",
            rationale="The evidence was reviewed.",
        )
        requirements = {item["code"]: item["status"] for item in gate["requirements"]}
        self.assertEqual(requirements["TEST_PASS"], "invalid")
        self.assertNotEqual(
            claim_status(self.project, "TECHNICALLY_VALIDATED"), "satisfied"
        )

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

    def test_a_script_parse_error_is_failed_even_when_godot_exits_zero(self) -> None:
        script = self.root / "main.gd"
        script.write_text(script.read_text() + "\nthis is invalid GDScript syntax\n")

        result = self.project.run_engine("build", expected_revision=None)

        self.assertEqual(result["run"]["status"], "failed")
        self.assertEqual(result["evidence"]["result"], "failed")
        self.assertTrue(result["run"]["engine_errors"])
        self.assertIn("Parse Error", result["run"]["stderr"])

    def test_a_playable_prototype_reaches_the_playtest_gate(self) -> None:
        """Exercise M2's full exit path against the real engine.

        The scene's deterministic seam exercises baseline scoring, the x3
        near-hazard reward, failure, and restart. A regression in any of those
        transitions exits non-zero. The gate is blocked before technical and
        visual evidence, then passes only after build, behavior-bearing startup,
        and capture evidence are all current for the approved hypothesis.
        """
        created = self.project.create_hypothesis(
            write_complete_hypothesis(self.root),
            expected_revision=1,
            approver_id="operator-1",
            approver_name="Fixture Operator",
            rationale="This is the bounded M2 representative experiment.",
        )
        self.assertEqual(created["committed_revision"], 2)
        self.assertEqual(self.project.gate_check("PROTOTYPING")["result"], "pass")
        advanced = self.project.advance("PROTOTYPING", expected_revision=2)
        self.assertEqual(advanced["committed_revision"], 3)

        with self.assertRaises(GateBlockedError):
            self.project.advance("PLAYTEST_REQUIRED", expected_revision=3)

        build = self.project.run_engine("build", expected_revision=3)
        self.assertEqual(build["committed_revision"], 5)
        with patch.dict("os.environ", {SELF_TEST_VARIABLE: "1"}):
            result = self.project.run_engine("test", expected_revision=5)

        self.assertEqual(result["run"]["status"], "completed", result["run"])
        self.assertEqual(result["run"]["exit_code"], 0, result["run"]["stderr"])
        self.assertEqual(result["evidence"]["result"], "passed")
        self.assertEqual(result["committed_revision"], 7)

        if platform.system() == "Linux" and shutil.which("xvfb-run") is None:
            self.skipTest("xvfb-run is required for real Linux runtime capture")
        frame = capture_fixture(self.root)
        capture = self.project.capture_screenshot(frame, expected_revision=7)
        self.assertEqual(capture["committed_revision"], 8)
        gate = self.project.gate_check("PLAYTEST_REQUIRED", **APPROVAL)
        self.assertEqual(gate["result"], "pass", gate)
        self.assertEqual(
            {item["code"] for item in gate["requirements"]},
            {"BUILD_PASS", "TEST_PASS", "CAPTURE_PRESENT", "HUMAN_APPROVAL"},
        )

        ready = self.project.advance(
            "PLAYTEST_REQUIRED", expected_revision=8, **APPROVAL
        )
        self.assertEqual(ready["committed_revision"], 9)
        self.assertEqual(self.project.status()["stage"], "PLAYTEST_REQUIRED")

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
        self.assertEqual(
            caught.exception.diagnostic_code, "ENGINE_PROJECT_NOT_DETECTED"
        )

    def test_a_project_icon_cannot_pass_as_a_runtime_capture(self) -> None:
        binary = godot_binary()
        self.assertIsNotNone(binary)
        result = subprocess.run(
            [
                binary,
                "--headless",
                "--path",
                str(self.root),
                "--script",
                "res://verify_capture.gd",
                "--",
                str(Path(__file__).resolve().parents[2] / "brand/png/favicon-16.png"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
