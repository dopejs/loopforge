from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALSET_ROOT = ROOT / "skills" / "evalsets"
M2_SKILLS = ("loopforge-router", "prototype-gameplay", "build-godot-game")


class MilestoneTwoEvalsetTests(unittest.TestCase):
    """Keep M2's human/LLM evaluation gate executable and reviewable.

    These tests do not pretend to replace the LLM judge. They protect the
    load-bearing inputs to that judge: unique tasks, resolvable skill context,
    explicit expected behavior, positive procedural coverage, and at least one
    negative trigger for every M2 skill.
    """

    def test_every_m2_skill_has_a_well_formed_evalset(self) -> None:
        for skill_name in M2_SKILLS:
            with self.subTest(skill=skill_name):
                path = EVALSET_ROOT / f"{skill_name}.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["skill"], skill_name)
                tasks = payload["tasks"]
                self.assertGreaterEqual(len(tasks), 4)
                identifiers = [task["id"] for task in tasks]
                self.assertEqual(len(identifiers), len(set(identifiers)))
                self.assertTrue(
                    any(
                        identifier.startswith("negative-") for identifier in identifiers
                    ),
                    f"{skill_name} needs an explicit negative trigger task",
                )

                skill_root = ROOT / "skills" / skill_name
                for task in tasks:
                    self.assertTrue(task["prompt"].strip())
                    self.assertTrue(task["expected_behavior"].strip())
                    self.assertIn("do not call tools", task["prompt"].lower())
                    self.assertTrue(task["skill_files"])
                    for relative in task["skill_files"]:
                        resolved = (skill_root / relative).resolve()
                        self.assertTrue(
                            resolved.is_relative_to(skill_root.resolve()),
                            f"{relative} escapes {skill_name}",
                        )
                        self.assertTrue(resolved.is_file(), str(resolved))


if __name__ == "__main__":
    unittest.main()
