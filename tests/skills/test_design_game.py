from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "skills" / "design-game" / "scripts" / "validate_design.py"


class DesignGameContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.contract_path = self.project / "design-contract.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def contract(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "project": {
                "experiment_id": "exp-test",
                "hypothesis_revision": 1,
                "project_revision": 5,
                "source_identity": "sha256:source",
                "platform": "desktop",
            },
            "design_document": {"path": "docs/game-design.md", "checksum": ""},
            "design_nucleus": {
                "summary": "Choose between immediate safety and multiplier growth.",
                "behavior_change": "Players deliberately remain near moving hazards.",
                "differentiator": "Risk changes route timing rather than only payout.",
                "prototype_evidence_ids": ["ev-playtest"],
            },
            "player_promise": {
                "marketing": "Dare hazards to turn narrow escapes into speed.",
                "first_10_minutes": "Discover and repeat a close-risk dash.",
                "long_term": "Master routes and build distinct risk strategies.",
            },
            "loops": {
                name: {
                    "goal": f"Complete the {name} objective.",
                    "actions": ["Observe", "Commit"],
                    "choice": "Take a safe route or expose the run to more risk.",
                    "risk": "A collision ends current progress.",
                    "feedback": "Danger, multiplier, and failure are visible.",
                    "reward": "Gain score, route knowledge, or an option.",
                    "next_constraint": "The next route has tighter timing.",
                }
                for name in ("moment", "session", "meta")
            },
            "scope": [
                {
                    "id": "core-loop",
                    "name": "Hazard dash loop",
                    "bucket": "mvp",
                    "proves": "Risk proximity changes player behavior.",
                    "dependencies": [],
                    "owner": "design",
                    "delete_condition": "Players do not intentionally repeat it.",
                },
                {
                    "id": "representative-slice",
                    "name": "One complete representative run",
                    "bucket": "vertical_slice",
                    "proves": "The final experience is readable and repeatable.",
                    "dependencies": ["core-loop"],
                    "owner": "team",
                    "delete_condition": "The core loop is invalidated.",
                },
            ],
            "systems": [
                {
                    "id": "risk-score",
                    "name": "Risk multiplier",
                    "serves_loop": "moment",
                    "scope_id": "core-loop",
                    "behavior_change": "Players charge closer to hazards.",
                    "inputs": ["distance", "charge time"],
                    "outputs": ["multiplier"],
                    "feedback": "Danger zone and multiplier tier are visible.",
                    "validation": "Observe intentional close charges.",
                    "delete_condition": "Players ignore proximity after discovery.",
                }
            ],
            "assumptions": [
                {
                    "id": "assumption-core",
                    "statement": "Risk multiplier produces intentional danger seeking.",
                    "confidence": "medium",
                    "impact": "high",
                    "status": "planned",
                    "verification": "External first-time playtest.",
                    "evidence_ids": [],
                }
            ],
            "risks": [
                {
                    "id": "risk-readability",
                    "cause": "Danger feedback competes with hazards.",
                    "impact": "Failures appear arbitrary.",
                    "mitigation": "Reserve value and motion hierarchy.",
                    "trigger": "Participants cannot explain collisions.",
                    "owner": "design",
                }
            ],
            "validation_plan": {
                "dangerous_assumption_ids": ["assumption-core"],
                "prototype": "One resettable arena and two hazards.",
                "pass_criteria": ["Four of six participants repeat close charges."],
                "fail_criteria": ["Two or fewer participants seek danger."],
                "next_investment_condition": "The primary behavior threshold passes.",
            },
            "approval": {
                "status": "pending",
                "approver_id": "",
                "approver_name": "",
                "rationale": "",
                "approved_at": "",
            },
        }

    def run_validator(
        self, contract: dict[str, object], *extra: str
    ) -> tuple[int, dict[str, object]]:
        self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--project",
                str(self.project),
                "--contract",
                str(self.contract_path),
                "--format",
                "json",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode, json.loads(result.stdout)

    def test_complete_pending_contract_is_structurally_valid(self) -> None:
        code, result = self.run_validator(self.contract())
        self.assertEqual(code, 0, result)
        self.assertTrue(result["valid"])

    def test_pending_approval_blocks_handoff_gate(self) -> None:
        code, result = self.run_validator(self.contract(), "--require-approved")
        self.assertEqual(code, 2)
        self.assertIn("APPROVAL_PENDING", self.error_codes(result))

    def test_approved_contract_requires_matching_document_checksum(self) -> None:
        contract = self.contract()
        document = self.project / "docs" / "game-design.md"
        document.parent.mkdir()
        document.write_text("# Approved design\n", encoding="utf-8")
        contract["design_document"]["checksum"] = (
            "sha256:" + hashlib.sha256(document.read_bytes()).hexdigest()
        )
        contract["approval"] = {
            "status": "approved",
            "approver_id": "local:designer",
            "approver_name": "Designer",
            "rationale": "The scope proves the selected nucleus.",
            "approved_at": "2026-08-18T10:00:00Z",
        }
        code, result = self.run_validator(contract, "--require-approved")
        self.assertEqual(code, 0, result)
        document.write_text("# Changed design\n", encoding="utf-8")
        code, result = self.run_validator(contract, "--require-approved")
        self.assertEqual(code, 2)
        self.assertIn("DOCUMENT_CHECKSUM", self.error_codes(result))

    def test_document_path_cannot_escape_project(self) -> None:
        contract = self.contract()
        contract["design_document"]["path"] = "../shared/design.md"
        code, result = self.run_validator(contract)
        self.assertEqual(code, 2)
        self.assertIn("DOCUMENT_PATH", self.error_codes(result))

    def test_duplicate_scope_and_dependency_cycle_are_rejected(self) -> None:
        contract = self.contract()
        contract["scope"][1]["id"] = "core-loop"
        contract["scope"][0]["dependencies"] = ["core-loop"]
        code, result = self.run_validator(contract)
        self.assertEqual(code, 2)
        self.assertIn("DUPLICATE_ID", self.error_codes(result))
        self.assertIn("SCOPE_CYCLE", self.error_codes(result))

    def test_unknown_system_scope_and_assumption_references_are_rejected(self) -> None:
        contract = self.contract()
        contract["systems"][0]["scope_id"] = "missing-scope"
        contract["validation_plan"]["dangerous_assumption_ids"] = ["missing-assumption"]
        code, result = self.run_validator(contract)
        self.assertEqual(code, 2)
        self.assertIn("SCOPE_REFERENCE", self.error_codes(result))
        self.assertIn("ASSUMPTION_REFERENCE", self.error_codes(result))

    def test_template_placeholders_are_rejected(self) -> None:
        template = json.loads(
            (
                ROOT / "skills" / "design-game" / "assets" / "design-contract.json"
            ).read_text()
        )
        code, result = self.run_validator(template)
        self.assertEqual(code, 2)
        self.assertIn("FIELD_REQUIRED", self.error_codes(result))

    @staticmethod
    def error_codes(result: dict[str, object]) -> set[str]:
        return {item["code"] for item in result["errors"]}


if __name__ == "__main__":
    unittest.main()
