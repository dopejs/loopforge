from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
EXPECTED_SKILLS = {
    "build-godot-game",
    "design-game",
    "direct-game-art",
    "loopforge-router",
    "prototype-gameplay",
}


def run_setup(
    skills_root: Path | None,
    *arguments: str,
    environment_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "cli")
    environment.update(environment_overrides or {})
    command = [PYTHON, "-m", "loopforge", "setup"]
    if skills_root is not None:
        command.extend(("--skills-root", str(skills_root)))
    command.extend(("--format", "json", *arguments))
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


class SkillInstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.skills_root = Path(self.temporary.name) / "codex-skills"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_setup_installs_all_bundled_skills_and_is_idempotent(self) -> None:
        installed = run_setup(self.skills_root)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        payload = json.loads(installed.stdout)
        self.assertEqual(payload["data"]["installed"], 5)
        self.assertEqual(
            {item["name"] for item in payload["data"]["skills"]},
            EXPECTED_SKILLS,
        )
        for name in EXPECTED_SKILLS:
            self.assertTrue((self.skills_root / name / "SKILL.md").is_file())
            marker = json.loads(
                (self.skills_root / name / ".loopforge-install.json").read_text()
            )
            self.assertEqual(marker["product"], "loopforge")
            self.assertTrue(marker["installed_digest"].startswith("sha256:"))

        repeated = run_setup(self.skills_root)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        payload = json.loads(repeated.stdout)
        self.assertEqual(payload["data"]["installed"], 0)
        self.assertEqual(payload["data"]["updated"], 0)
        self.assertEqual(payload["data"]["skipped"], 5)

    def test_setup_dry_run_does_not_write(self) -> None:
        result = run_setup(self.skills_root, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["data"]["dry_run"])
        self.assertEqual(payload["data"]["installed"], 5)
        self.assertFalse(self.skills_root.exists())

    def test_setup_uses_codex_home_by_default(self) -> None:
        codex_home = Path(self.temporary.name) / "codex-home"
        result = run_setup(
            None,
            environment_overrides={"CODEX_HOME": str(codex_home)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["data"]["skills_root"], str((codex_home / "skills").resolve())
        )
        self.assertEqual(
            {path.name for path in (codex_home / "skills").iterdir()},
            EXPECTED_SKILLS,
        )

    def test_setup_blocks_modified_skill_without_partial_install(self) -> None:
        conflict = self.skills_root / "build-godot-game"
        conflict.mkdir(parents=True)
        (conflict / "SKILL.md").write_text("local custom Skill\n")

        result = run_setup(self.skills_root)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["diagnostics"][0]["code"], "SKILL_INSTALL_CONFLICT")
        self.assertEqual((conflict / "SKILL.md").read_text(), "local custom Skill\n")
        self.assertEqual(
            [path.name for path in self.skills_root.iterdir()],
            ["build-godot-game"],
        )

    def test_force_preserves_modified_skill_as_backup(self) -> None:
        installed = run_setup(self.skills_root)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        custom = self.skills_root / "design-game" / "SKILL.md"
        custom.write_text(custom.read_text() + "\nlocal customization\n")

        blocked = run_setup(self.skills_root)
        self.assertEqual(blocked.returncode, 2)

        forced = run_setup(self.skills_root, "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        payload = json.loads(forced.stdout)
        design = next(
            item for item in payload["data"]["skills"] if item["name"] == "design-game"
        )
        self.assertEqual(design["action"], "update")
        backup = Path(design["backup"])
        self.assertTrue(backup.is_dir())
        self.assertIn("local customization", (backup / "SKILL.md").read_text())
        self.assertNotIn("local customization", custom.read_text())

    def test_uninstall_removes_only_unmodified_managed_skills(self) -> None:
        installed = run_setup(self.skills_root)
        self.assertEqual(installed.returncode, 0, installed.stderr)

        removed = run_setup(self.skills_root, "--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        payload = json.loads(removed.stdout)
        self.assertEqual(payload["data"]["removed"], 5)
        self.assertEqual(payload["data"]["skipped"], 0)
        self.assertEqual(list(self.skills_root.iterdir()), [])

        repeated = run_setup(self.skills_root, "--uninstall")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        payload = json.loads(repeated.stdout)
        self.assertEqual(payload["data"]["removed"], 0)
        self.assertEqual(payload["data"]["skipped"], 5)

    def test_uninstall_blocks_local_changes_and_force_preserves_backup(self) -> None:
        installed = run_setup(self.skills_root)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        custom = self.skills_root / "direct-game-art" / "SKILL.md"
        custom.write_text(custom.read_text() + "\nlocal customization\n")

        blocked = run_setup(self.skills_root, "--uninstall")
        self.assertEqual(blocked.returncode, 2)
        payload = json.loads(blocked.stdout)
        self.assertEqual(payload["diagnostics"][0]["code"], "SKILL_UNINSTALL_CONFLICT")
        self.assertTrue(custom.is_file())

        forced = run_setup(self.skills_root, "--uninstall", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        payload = json.loads(forced.stdout)
        art = next(
            item
            for item in payload["data"]["skills"]
            if item["name"] == "direct-game-art"
        )
        backup = Path(art["backup"])
        self.assertFalse((self.skills_root / "direct-game-art").exists())
        self.assertIn("local customization", (backup / "SKILL.md").read_text())


if __name__ == "__main__":
    unittest.main()
