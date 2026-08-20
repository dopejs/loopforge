from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "prototype-gameplay" / "scripts" / "prepare_workspace.py"
VALIDATOR = ROOT / "skills" / "prototype-gameplay" / "scripts" / "validate_draft.py"


def run_script(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project", str(project), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def validate_draft(artifact: str, file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--artifact",
            artifact,
            "--file",
            str(file),
            "--format",
            "json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class PrototypeWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def initialize(self) -> None:
        state_dir = self.project / ".loopforge"
        state_dir.mkdir()
        (state_dir / "project.json").write_text("{}\n")
        (state_dir / "events.jsonl").write_text("")

    def test_requires_initialized_project(self) -> None:
        result = run_script(
            self.project,
            "--artifact",
            "hypothesis",
            "--format",
            "json",
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["diagnostics"][0]["code"], "PROJECT_NOT_INITIALIZED")
        self.assertFalse((self.project / ".loopforge" / "drafts").exists())

    def test_all_artifacts_are_created_and_rerun_is_idempotent(self) -> None:
        self.initialize()
        first = run_script(self.project, "--artifact", "all", "--format", "json")
        self.assertEqual(first.returncode, 0, first.stderr)
        first_payload = json.loads(first.stdout)
        self.assertEqual(len(first_payload["artifacts"]), 5)
        self.assertEqual(
            {item["action"] for item in first_payload["artifacts"]}, {"created"}
        )

        second = run_script(self.project, "--artifact", "all", "--format", "json")
        self.assertEqual(second.returncode, 0, second.stderr)
        second_payload = json.loads(second.stdout)
        self.assertEqual(
            {item["action"] for item in second_payload["artifacts"]}, {"unchanged"}
        )

    def test_changed_draft_requires_force_and_is_not_partially_written(self) -> None:
        self.initialize()
        created = run_script(self.project, "--artifact", "all")
        self.assertEqual(created.returncode, 0, created.stderr)
        draft = self.project / ".loopforge" / "drafts" / "hypothesis.md"
        draft.write_text("human edit\n")
        untouched = self.project / ".loopforge" / "drafts" / "prototype-brief.md"
        before = untouched.read_bytes()

        conflict = run_script(self.project, "--artifact", "all", "--format", "json")
        self.assertEqual(conflict.returncode, 2)
        self.assertEqual(
            json.loads(conflict.stdout)["diagnostics"][0]["code"], "DRAFT_CONFLICT"
        )
        self.assertEqual(draft.read_text(), "human edit\n")
        self.assertEqual(untouched.read_bytes(), before)

        replaced = run_script(
            self.project,
            "--artifact",
            "hypothesis",
            "--force",
            "--format",
            "json",
        )
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertEqual(
            json.loads(replaced.stdout)["artifacts"][0]["action"], "replaced"
        )
        self.assertIn("## Hypothesis", draft.read_text())

    def test_output_cannot_escape_project(self) -> None:
        self.initialize()
        outside = self.project.parent / "outside.md"
        result = run_script(
            self.project,
            "--artifact",
            "hypothesis",
            "--output",
            str(outside),
            "--format",
            "json",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["diagnostics"][0]["code"],
            "OUTPUT_OUTSIDE_PROJECT",
        )
        self.assertFalse(outside.exists())

    def test_unfilled_template_is_rejected(self) -> None:
        template = ROOT / "skills" / "prototype-gameplay" / "assets" / "hypothesis.md"
        result = validate_draft("hypothesis", template)
        self.assertEqual(result.returncode, 2)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("DRAFT_PLACEHOLDERS_REMAIN", codes)

    def test_completed_hypothesis_is_valid(self) -> None:
        draft = self.project / "hypothesis.md"
        headings = (
            "Intended player",
            "Platform",
            "Player fantasy",
            "Core verb",
            "Moment to moment loop",
            "Hypothesis",
            "Constraints",
            "Non-goals",
            "Cheapest validation",
            "Keep signals",
            "Kill signals",
            "Approval checkpoint",
        )
        draft.write_text(
            "\n\n".join(f"## {heading}\nConcrete {heading}." for heading in headings)
        )
        result = validate_draft("hypothesis", draft)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_playtest_report_requires_real_observations_and_no_placeholders(
        self,
    ) -> None:
        report = self.project / "report.json"
        report.write_text(
            json.dumps(
                {
                    "build_identity": "sha256:tested-build",
                    "participant_context": "First exposure; experienced action player.",
                    "consent_status": "obtained",
                    "assistance_given": "None.",
                    "raw_observations": ["Used charge after 14 seconds."],
                    "comprehension_time": "14 seconds",
                    "confusion_points": [],
                    "failure_points": ["Hit the first hazard."],
                    "abandonment_points": [],
                    "strategies": ["Waited for the hazard to pass."],
                    "replay_behavior": "Restarted once without prompting.",
                    "interpretation": (
                        "One participant understood the timing risk; sample is limited."
                    ),
                    "sensitive_data": "None; anonymous notes deleted after decision.",
                }
            )
        )
        valid = validate_draft("playtest-report", report)
        self.assertEqual(valid.returncode, 0, valid.stderr)

        payload = json.loads(report.read_text())
        payload["raw_observations"] = ["<Add observation>"]
        report.write_text(json.dumps(payload))
        invalid = validate_draft("playtest-report", report)
        self.assertEqual(invalid.returncode, 2)
        codes = {item["code"] for item in json.loads(invalid.stdout)["diagnostics"]}
        self.assertIn("DRAFT_PLACEHOLDERS_REMAIN", codes)

        payload["raw_observations"] = ["Used charge after 14 seconds."]
        del payload["build_identity"]
        report.write_text(json.dumps(payload))
        incomplete = validate_draft("playtest-report", report)
        self.assertEqual(incomplete.returncode, 2)
        diagnostics = json.loads(incomplete.stdout)["diagnostics"]
        missing = next(
            item for item in diagnostics if item["code"] == "PLAYTEST_FIELDS_MISSING"
        )
        self.assertEqual(missing["details"]["fields"], ["build_identity"])


if __name__ == "__main__":
    unittest.main()
