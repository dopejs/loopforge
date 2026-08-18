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
sys.path.insert(0, str(ROOT / "cli"))
from loopforge.locking import ProjectLock
from loopforge.storage import EventStore


def run_cli(
    project: Path,
    *arguments: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "cli")
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        [PYTHON, "-m", "loopforge", "--project", str(project), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


class Milestone1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_hypothesis(self, complete: bool = True) -> Path:
        path = self.project / "hypothesis.md"
        sections = {
            "Intended player": "A solo player who likes readable risk and reward.",
            "Platform": "Desktop web prototype.",
            "Player fantasy": "I am threading a dangerous timing window.",
            "Core verb": "Charge and release.",
            "Moment to moment loop": "Observe hazard, charge, release, recover.",
            "Hypothesis": "Players will repeat the charge when the reward is visible.",
            "Constraints": "One screen and one minute sessions.",
            "Non-goals": "No progression or online services.",
            "Cheapest validation": "A greybox single-screen playable experiment.",
            "Keep signals": "Players retry without being prompted.",
            "Kill signals": "Players cannot explain the risk or stop after one try.",
        }
        if not complete:
            sections.pop("Kill signals")
        path.write_text(
            "\n\n".join(f"## {heading}\n{value}" for heading, value in sections.items())
            + "\n",
            encoding="utf-8",
        )
        return path

    def enter_prototyping(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        hypothesis = self.write_hypothesis()
        created = run_cli(
            self.project,
            "hypothesis",
            "create",
            "--file",
            str(hypothesis),
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "The experiment is narrow and falsifiable.",
            "--expected-revision",
            "1",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        advanced = run_cli(
            self.project,
            "advance",
            "PROTOTYPING",
            "--expected-revision",
            "2",
        )
        self.assertEqual(advanced.returncode, 0, advanced.stderr)

    def enter_early_decision(self) -> str:
        self.enter_prototyping()
        evidence_file = self.project / "technical-failure.txt"
        evidence_file.write_text("The target renderer cannot meet the frame budget.\n")
        added = run_cli(
            self.project,
            "evidence",
            "add",
            "--type",
            "technical",
            "--result",
            "failed",
            "--file",
            str(evidence_file),
            "--expected-revision",
            "3",
            "--format",
            "json",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        evidence_id = json.loads(added.stdout)["data"]["evidence"]["evidence_id"]
        advanced = run_cli(
            self.project,
            "advance",
            "PROTOTYPE_DECISION",
            "--reason",
            "technical",
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "The technical limit invalidates the current approach.",
            "--expected-revision",
            "4",
        )
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        return evidence_id

    def test_init_is_idempotent_and_status_is_machine_readable(self) -> None:
        first = run_cli(self.project, "--format", "json", "init")
        self.assertEqual(first.returncode, 0, first.stderr)
        first_payload = json.loads(first.stdout)
        self.assertTrue(first_payload["data"]["created"])
        self.assertEqual(first_payload["committed_revision"], 1)

        second = run_cli(self.project, "--format", "json", "init")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse(json.loads(second.stdout)["data"]["created"])

        status = run_cli(self.project, "status", "--format", "json")
        self.assertEqual(status.returncode, 0, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["data"]["stage"], "DISCOVERY")
        self.assertEqual(payload["observed_revision"], 1)
        self.assertEqual(payload["data"]["snapshot_status"], "current")

    def test_event_log_is_hash_chained_and_history_is_replayable(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        events_path = self.project / ".loopforge" / "events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["revision"], 1)
        self.assertIsNone(events[0]["previous_event_hash"])

        history = run_cli(self.project, "history", "--format", "json")
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertEqual(json.loads(history.stdout)["data"]["events"], events)

    def test_doctor_accepts_initialized_godot_4_project(self) -> None:
        (self.project / "project.godot").write_text(
            '[application]\nrun/main_scene="res://main.tscn"\n'
        )
        (self.project / "main.tscn").write_text("[gd_scene format=3]\n")
        fake_bin = self.project / "fake-bin"
        fake_bin.mkdir()
        fake_godot = fake_bin / "godot"
        fake_godot.write_text(
            '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "4.4.stable"; fi\nexit 0\n'
        )
        fake_godot.chmod(0o755)
        self.assertEqual(run_cli(self.project, "init").returncode, 0)

        result = run_cli(
            self.project,
            "doctor",
            "--format",
            "json",
            extra_env={"PATH": str(fake_bin)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["data"]["healthy"])
        statuses = {
            check["code"]: check["status"] for check in payload["data"]["checks"]
        }
        self.assertEqual(statuses["PROJECT_INTEGRITY"], "passed")
        self.assertEqual(statuses["GODOT_VERSION"], "passed")
        self.assertEqual(statuses["GODOT_MAIN_SCENE"], "passed")

    def test_doctor_reports_missing_godot_without_traceback(self) -> None:
        (self.project / "project.godot").write_text(
            '[application]\nrun/main_scene="res://main.tscn"\n'
        )
        (self.project / "main.tscn").write_text("[gd_scene format=3]\n")
        empty_bin = self.project / "empty-bin"
        empty_bin.mkdir()

        result = run_cli(
            self.project,
            "doctor",
            "--format",
            "json",
            extra_env={"PATH": str(empty_bin)},
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["data"]["healthy"])
        self.assertIn(
            "REQUIRED_TOOL_UNAVAILABLE",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_doctor_reports_missing_godot_main_scene(self) -> None:
        (self.project / "project.godot").write_text(
            '[application]\nconfig/name="Fixture"\n'
        )
        fake_bin = self.project / "fake-bin"
        fake_bin.mkdir()
        fake_godot = fake_bin / "godot4"
        fake_godot.write_text('#!/bin/sh\necho "4.3.stable"\n')
        fake_godot.chmod(0o755)

        result = run_cli(
            self.project,
            "doctor",
            "--format",
            "json",
            extra_env={"PATH": str(fake_bin)},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "GODOT_MAIN_SCENE_MISSING",
            {item["code"] for item in json.loads(result.stdout)["diagnostics"]},
        )

    def test_doctor_warns_about_completed_run_without_evidence(self) -> None:
        store = EventStore(self.project)
        store.initialize()
        run_dir = self.project / ".loopforge" / "runs"
        run_dir.mkdir()
        (run_dir / "orphan.json").write_text("{}\n")
        store.commit(
            "run.completed",
            {"run": {"run_id": "run_interrupted"}},
            expected_revision=1,
            run_id="run_interrupted",
        )
        result = run_cli(self.project, "doctor", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        warning = next(
            item
            for item in payload["diagnostics"]
            if item["code"] == "RUN_EVIDENCE_MISSING"
        )
        self.assertEqual(warning["severity"], "warning")
        orphan = next(
            item
            for item in payload["diagnostics"]
            if item["code"] == "ORPHAN_RUN_ARTIFACT"
        )
        self.assertEqual(orphan["details"]["paths"], [".loopforge/runs/orphan.json"])

    def test_stale_snapshot_requires_reconcile(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        state_path = self.project / ".loopforge" / "state.json"
        state = json.loads(state_path.read_text())
        state["stage"] = "CORRUPTED"
        state_path.write_text(json.dumps(state))

        validate = run_cli(self.project, "validate", "--format", "json")
        self.assertEqual(validate.returncode, 2)
        self.assertEqual(
            json.loads(validate.stdout)["diagnostics"][0]["code"],
            "STATE_SNAPSHOT_NOT_CURRENT",
        )

        dry_run = run_cli(self.project, "reconcile", "--dry-run", "--format", "json")
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertTrue(json.loads(dry_run.stdout)["data"]["actions"])

        apply = run_cli(self.project, "reconcile", "--yes", "--format", "json")
        self.assertEqual(apply.returncode, 0, apply.stderr)
        self.assertEqual(
            json.loads(apply.stdout)["data"]["snapshot_status"],
            "current",
        )
        self.assertEqual(run_cli(self.project, "validate").returncode, 0)

    def test_repeated_init_does_not_repair_stale_snapshot(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        state_path = self.project / ".loopforge" / "state.json"
        state = json.loads(state_path.read_text())
        state["stage"] = "CORRUPTED"
        state_path.write_text(json.dumps(state))
        result = run_cli(self.project, "init", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(state_path.read_text())["stage"], "CORRUPTED")

    def test_hash_corruption_fails_without_silent_repair(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        events_path = self.project / ".loopforge" / "events.jsonl"
        raw = events_path.read_text()
        events_path.write_text(raw.replace('"stage":"DISCOVERY"', '"stage":"BROKEN"'))

        result = run_cli(self.project, "validate", "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["diagnostics"][0]["code"],
            "EVENT_HASH_INVALID",
        )

    def test_evidence_records_checksum_and_source_identity(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        artifact = self.project / "capture.txt"
        artifact.write_text("playable evidence\n")

        add = run_cli(
            self.project,
            "evidence",
            "add",
            "--type",
            "capture",
            "--file",
            str(artifact),
            "--format",
            "json",
            "--expected-revision",
            "1",
        )
        self.assertEqual(add.returncode, 0, add.stderr)
        payload = json.loads(add.stdout)
        self.assertEqual(payload["committed_revision"], 2)
        record = payload["data"]["evidence"]
        self.assertEqual(record["trust_level"], "manually_imported")
        self.assertTrue(record["artifact"]["checksum"].startswith("sha256:"))
        self.assertIn(record["source_identity"]["kind"], {"git", "project-fingerprint"})

        listing = run_cli(self.project, "evidence", "list", "--format", "json")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(len(json.loads(listing.stdout)["data"]["evidence"]), 1)

    def test_quality_claims_become_satisfied_then_stale_after_source_change(
        self,
    ) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        initial = json.loads(run_cli(self.project, "status", "--format", "json").stdout)
        self.assertEqual(
            initial["data"]["claims"]["TECHNICALLY_VALIDATED"]["status"], "unknown"
        )

        artifact = self.project.parent / f"{self.project.name}-claim-artifact.log"
        artifact.write_text("stable evidence\n")
        try:
            for revision, evidence_type in enumerate(
                ("build", "test", "capture"), start=1
            ):
                result = run_cli(
                    self.project,
                    "evidence",
                    "add",
                    "--type",
                    evidence_type,
                    "--result",
                    "observation" if evidence_type == "capture" else "passed",
                    "--file",
                    str(artifact),
                    "--expected-revision",
                    str(revision),
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            current = json.loads(
                run_cli(self.project, "status", "--format", "json").stdout
            )
            claims = current["data"]["claims"]
            self.assertEqual(claims["TECHNICALLY_VALIDATED"]["status"], "satisfied")
            self.assertEqual(len(claims["TECHNICALLY_VALIDATED"]["evidence_ids"]), 2)
            self.assertEqual(claims["VISUALLY_REVIEWED"]["status"], "satisfied")

            (self.project / "game.gd").write_text("extends Node\n")
            stale = json.loads(
                run_cli(self.project, "status", "--format", "json").stdout
            )
            self.assertEqual(
                stale["data"]["claims"]["TECHNICALLY_VALIDATED"]["status"], "stale"
            )
            self.assertEqual(
                stale["data"]["claims"]["VISUALLY_REVIEWED"]["status"], "stale"
            )
        finally:
            artifact.unlink(missing_ok=True)

    def test_validate_reports_mutated_and_deleted_evidence_artifacts(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        artifact = self.project / "evidence.txt"
        artifact.write_text("original\n")
        added = run_cli(
            self.project,
            "evidence",
            "add",
            "--type",
            "other",
            "--file",
            str(artifact),
            "--expected-revision",
            "1",
        )
        self.assertEqual(added.returncode, 0, added.stderr)

        artifact.write_text("mutated\n")
        mutated = run_cli(self.project, "validate", "--format", "json")
        self.assertEqual(mutated.returncode, 2)
        mutated_codes = {
            item["code"] for item in json.loads(mutated.stdout)["diagnostics"]
        }
        self.assertIn("EVIDENCE_CHECKSUM_INVALID", mutated_codes)

        artifact.unlink()
        deleted = run_cli(self.project, "validate", "--format", "json")
        self.assertEqual(deleted.returncode, 2)
        deleted_codes = {
            item["code"] for item in json.loads(deleted.stdout)["diagnostics"]
        }
        self.assertIn("EVIDENCE_ARTIFACT_MISSING", deleted_codes)

    def test_stale_expected_revision_does_not_write(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        artifact = self.project / "evidence.txt"
        artifact.write_text("evidence")
        result = run_cli(
            self.project,
            "evidence",
            "add",
            "--type",
            "other",
            "--file",
            str(artifact),
            "--expected-revision",
            "0",
            "--format",
            "json",
        )
        self.assertEqual(result.returncode, 5)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["diagnostics"][0]["code"], "EXPECTED_REVISION_MISMATCH"
        )
        history = run_cli(self.project, "history", "--format", "json")
        self.assertEqual(len(json.loads(history.stdout)["data"]["events"]), 1)

    def test_live_project_lock_returns_conflict_without_writing(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        artifact = self.project / "evidence.txt"
        artifact.write_text("evidence")
        lock_path = self.project / ".loopforge" / "lock"
        with ProjectLock(lock_path):
            result = run_cli(
                self.project,
                "evidence",
                "add",
                "--type",
                "other",
                "--file",
                str(artifact),
                "--format",
                "json",
            )
        self.assertEqual(result.returncode, 5)
        self.assertEqual(
            json.loads(result.stdout)["diagnostics"][0]["code"], "PROJECT_LOCKED"
        )
        history = run_cli(self.project, "history", "--format", "json")
        self.assertEqual(len(json.loads(history.stdout)["data"]["events"]), 1)

    def test_torn_final_event_is_reported_not_repaired(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        events_path = self.project / ".loopforge" / "events.jsonl"
        raw = events_path.read_bytes()
        events_path.write_bytes(raw[:-1])
        result = run_cli(self.project, "validate", "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["diagnostics"][0]["code"],
            "EVENT_LOG_TORN_WRITE",
        )

    def test_hypothesis_gate_and_advance(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        blocked = run_cli(
            self.project, "gate", "check", "PROTOTYPING", "--format", "json"
        )
        self.assertEqual(blocked.returncode, 3)
        blocked_payload = json.loads(blocked.stdout)
        self.assertEqual(blocked_payload["command"], "gate.check")
        self.assertEqual(blocked_payload["data"]["result"], "blocked")

        hypothesis = self.write_hypothesis()
        created = run_cli(
            self.project,
            "hypothesis",
            "create",
            "--file",
            str(hypothesis),
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "The question is narrow enough to test.",
            "--expected-revision",
            "1",
            "--format",
            "json",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        created_payload = json.loads(created.stdout)
        self.assertEqual(created_payload["committed_revision"], 2)
        self.assertEqual(
            created_payload["data"]["hypothesis"]["approval"]["approver_id"],
            "local:test",
        )

        gate = run_cli(self.project, "gate", "check", "PROTOTYPING", "--format", "json")
        self.assertEqual(gate.returncode, 0, gate.stderr)
        self.assertEqual(json.loads(gate.stdout)["data"]["result"], "pass")

        advance = run_cli(
            self.project,
            "advance",
            "PROTOTYPING",
            "--expected-revision",
            "2",
            "--format",
            "json",
        )
        self.assertEqual(advance.returncode, 0, advance.stderr)
        self.assertEqual(json.loads(advance.stdout)["committed_revision"], 3)
        status = run_cli(self.project, "status", "--format", "json")
        self.assertEqual(json.loads(status.stdout)["data"]["stage"], "PROTOTYPING")

    def test_incomplete_hypothesis_is_rejected_before_event_commit(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        hypothesis = self.write_hypothesis(complete=False)
        result = run_cli(
            self.project,
            "hypothesis",
            "create",
            "--file",
            str(hypothesis),
            "--format",
            "json",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["diagnostics"][0]["code"],
            "HYPOTHESIS_SCHEMA_INVALID",
        )
        history = run_cli(self.project, "history", "--format", "json")
        self.assertEqual(len(json.loads(history.stdout)["data"]["events"]), 1)

    def test_latest_failed_build_blocks_playtest_gate(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        hypothesis = self.write_hypothesis()
        created = run_cli(
            self.project,
            "hypothesis",
            "create",
            "--file",
            str(hypothesis),
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "Testable.",
            "--expected-revision",
            "1",
            "--format",
            "json",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(
            run_cli(
                self.project,
                "advance",
                "PROTOTYPING",
                "--expected-revision",
                "2",
            ).returncode,
            0,
        )
        external = self.project.parent / f"{self.project.name}-build.log"
        external.write_text("build result")
        try:
            passed = run_cli(
                self.project,
                "evidence",
                "add",
                "--type",
                "build",
                "--result",
                "passed",
                "--file",
                str(external),
                "--expected-revision",
                "3",
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            failed = run_cli(
                self.project,
                "evidence",
                "add",
                "--type",
                "build",
                "--result",
                "failed",
                "--file",
                str(external),
                "--expected-revision",
                "4",
                "--format",
                "json",
            )
            self.assertEqual(failed.returncode, 0, failed.stderr)
            gate = run_cli(
                self.project,
                "gate",
                "check",
                "PLAYTEST_REQUIRED",
                "--format",
                "json",
            )
            self.assertEqual(gate.returncode, 3)
            requirements = json.loads(gate.stdout)["data"]["requirements"]
            build = next(item for item in requirements if item["code"] == "BUILD_PASS")
            self.assertEqual(build["status"], "failed")
        finally:
            external.unlink(missing_ok=True)

    def test_multiple_evidence_records_share_source_identity_when_only_state_changes(
        self,
    ) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        artifact = self.project.parent / f"{self.project.name}-artifact.log"
        artifact.write_text("stable external artifact")
        try:
            identities = []
            revision = 1
            for evidence_type in ("build", "test", "capture"):
                result = run_cli(
                    self.project,
                    "evidence",
                    "add",
                    "--type",
                    evidence_type,
                    "--result",
                    "passed" if evidence_type != "capture" else "observation",
                    "--file",
                    str(artifact),
                    "--expected-revision",
                    str(revision),
                    "--format",
                    "json",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                identities.append(
                    json.loads(result.stdout)["data"]["evidence"]["source_identity"]
                )
                revision += 1
            self.assertEqual(identities[0], identities[1])
            self.assertEqual(identities[1], identities[2])
        finally:
            artifact.unlink(missing_ok=True)

    def test_fake_godot_run_records_tool_generated_evidence(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        (self.project / "project.godot").write_text(
            "[application]\nconfig/name=Fixture\n"
        )
        fake_bin = self.project / "fake-bin"
        fake_bin.mkdir()
        fake_godot = fake_bin / "godot"
        fake_godot.write_text(
            '#!/bin/sh\nif [ "$1" = "--version" ]; then echo \'Godot Fake 4.0\'; fi\nexit 0\n'
        )
        fake_godot.chmod(0o755)
        environment = {"PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
        result = run_cli(
            self.project,
            "run",
            "build",
            "--expected-revision",
            "1",
            "--format",
            "json",
            extra_env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["committed_revision"], 3)
        self.assertEqual(payload["data"]["evidence"]["trust_level"], "tool_generated")
        self.assertEqual(payload["data"]["run"]["status"], "completed")

        history = run_cli(self.project, "history", "--format", "json")
        event_types = [
            event["event_type"]
            for event in json.loads(history.stdout)["data"]["events"]
        ]
        self.assertEqual(
            event_types, ["project.initialized", "run.completed", "evidence.registered"]
        )

    def test_complete_keep_path_from_hypothesis_to_decision(self) -> None:
        (self.project / "project.godot").write_text(
            "[application]\nconfig/name=Fixture\n"
        )
        fake_bin = self.project / "fake-bin"
        fake_bin.mkdir()
        fake_godot = fake_bin / "godot"
        fake_godot.write_text(
            '#!/bin/sh\nif [ "$1" = "--version" ]; then echo \'Godot Fake 4.0\'; fi\nexit 0\n'
        )
        fake_godot.chmod(0o755)
        environment = {"PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        hypothesis = self.write_hypothesis()
        create = run_cli(
            self.project,
            "hypothesis",
            "create",
            "--file",
            str(hypothesis),
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "Narrow test.",
            "--expected-revision",
            "1",
            "--format",
            "json",
        )
        self.assertEqual(create.returncode, 0, create.stderr)
        advance = run_cli(
            self.project, "advance", "PROTOTYPING", "--expected-revision", "2"
        )
        self.assertEqual(advance.returncode, 0, advance.stderr)

        build = run_cli(
            self.project,
            "run",
            "build",
            "--expected-revision",
            "3",
            "--format",
            "json",
            extra_env=environment,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        test_run = run_cli(
            self.project,
            "run",
            "test",
            "--expected-revision",
            "5",
            "--format",
            "json",
            extra_env=environment,
        )
        self.assertEqual(test_run.returncode, 0, test_run.stderr)
        screenshot = self.project / "screenshot.png"
        protocol = self.project.parent / f"{self.project.name}-protocol.md"
        report = self.project.parent / f"{self.project.name}-report.json"
        screenshot.write_bytes(b"fake png")
        protocol.write_text("Observe controls without coaching.\n")
        report.write_text(
            json.dumps(
                {
                    "participant_context": "Experienced developer, first exposure to this build.",
                    "consent_status": "obtained",
                    "raw_observations": ["Started charging after seeing the hazard."],
                    "comprehension_time": "42 seconds",
                    "confusion_points": [],
                    "failure_points": ["Missed the first timing window."],
                    "abandonment_points": [],
                    "strategies": ["Waited for a safe opening."],
                    "replay_behavior": "Retried twice without prompting.",
                    "interpretation": "The risk was understood and the reward was visible.",
                }
            )
        )
        try:
            capture = run_cli(
                self.project,
                "capture",
                "screenshot",
                "--file",
                str(screenshot),
                "--expected-revision",
                "7",
                "--format",
                "json",
            )
            self.assertEqual(capture.returncode, 0, capture.stderr)
            self.assertEqual(
                run_cli(self.project, "gate", "check", "PLAYTEST_REQUIRED").returncode,
                0,
            )
            self.assertEqual(
                run_cli(
                    self.project,
                    "advance",
                    "PLAYTEST_REQUIRED",
                    "--expected-revision",
                    "8",
                ).returncode,
                0,
            )
            protocol_result = run_cli(
                self.project,
                "playtest",
                "create",
                "--protocol",
                str(protocol),
                "--expected-revision",
                "9",
                "--format",
                "json",
            )
            self.assertEqual(protocol_result.returncode, 0, protocol_result.stderr)
            imported = run_cli(
                self.project,
                "playtest",
                "import",
                "--file",
                str(report),
                "--expected-revision",
                "10",
                "--format",
                "json",
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertEqual(
                run_cli(self.project, "gate", "check", "PROTOTYPE_DECISION").returncode,
                0,
            )
            self.assertEqual(
                run_cli(
                    self.project,
                    "advance",
                    "PROTOTYPE_DECISION",
                    "--expected-revision",
                    "11",
                ).returncode,
                0,
            )
            bypass = run_cli(
                self.project,
                "advance",
                "KILLED",
                "--expected-revision",
                "12",
                "--format",
                "json",
            )
            self.assertEqual(bypass.returncode, 3)
            evidence = json.loads(
                run_cli(self.project, "evidence", "list", "--format", "json").stdout
            )["data"]["evidence"]
            evidence_ids = [record["evidence_id"] for record in evidence]
            decision = run_cli(
                self.project,
                "decide",
                "keep",
                "--evidence",
                evidence_ids[-1],
                "--approver-id",
                "local:test",
                "--approver-name",
                "Test User",
                "--rationale",
                "Observed comprehension and voluntary replay.",
                "--expected-revision",
                "12",
                "--format",
                "json",
            )
            self.assertEqual(decision.returncode, 0, decision.stderr)
            status = json.loads(
                run_cli(self.project, "status", "--format", "json").stdout
            )
            self.assertEqual(status["data"]["stage"], "VERTICAL_SLICE")
            self.assertEqual(
                status["data"]["claims"]["FUN_HYPOTHESIS_SUPPORTED"]["status"],
                "satisfied",
            )
            self.assertTrue(
                status["data"]["claims"]["FUN_HYPOTHESIS_SUPPORTED"][
                    "decision_event_ids"
                ]
            )
        finally:
            screenshot.unlink(missing_ok=True)
            protocol.unlink(missing_ok=True)
            report.unlink(missing_ok=True)

    def test_refactor_creates_hypothesis_revision_two_and_returns_to_prototyping(
        self,
    ) -> None:
        evidence_id = self.enter_early_decision()
        revised = self.write_hypothesis()
        revised.write_text(
            revised.read_text().replace(
                "Players will repeat the charge when the reward is visible.",
                "Players will repeat a shorter charge when recovery is immediate.",
            )
        )
        decision = run_cli(
            self.project,
            "decide",
            "refactor",
            "--file",
            str(revised),
            "--evidence",
            evidence_id,
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "Shorten the charge and test immediate recovery.",
            "--expected-revision",
            "5",
            "--format",
            "json",
        )
        self.assertEqual(decision.returncode, 0, decision.stderr)
        status = json.loads(run_cli(self.project, "status", "--format", "json").stdout)
        self.assertEqual(status["data"]["stage"], "PROTOTYPING")
        self.assertEqual(status["data"]["active_experiment"]["hypothesis_revision"], 2)
        shown = json.loads(
            run_cli(self.project, "hypothesis", "show", "--format", "json").stdout
        )
        self.assertEqual(shown["data"]["hypothesis"]["revision"], 2)
        self.assertEqual(run_cli(self.project, "validate").returncode, 0)

    def test_early_technical_decision_can_kill_the_prototype(self) -> None:
        evidence_id = self.enter_early_decision()
        decision = run_cli(
            self.project,
            "decide",
            "kill",
            "--evidence",
            evidence_id,
            "--approver-id",
            "local:test",
            "--approver-name",
            "Test User",
            "--rationale",
            "The target frame budget is infeasible for this approach.",
            "--expected-revision",
            "5",
            "--format",
            "json",
        )
        self.assertEqual(decision.returncode, 0, decision.stderr)
        status = json.loads(run_cli(self.project, "status", "--format", "json").stdout)
        self.assertEqual(status["data"]["stage"], "KILLED")
        self.assertEqual(
            status["data"]["claims"]["FUN_HYPOTHESIS_SUPPORTED"]["status"], "failed"
        )

    def test_malformed_event_payload_returns_diagnostic(self) -> None:
        self.assertEqual(run_cli(self.project, "init").returncode, 0)
        events_path = self.project / ".loopforge" / "events.jsonl"
        event = json.loads(events_path.read_text())
        event["payload"] = {"stage": "DISCOVERY"}
        # Deliberately leave the old hash in place: the CLI must report a
        # structured integrity error rather than exposing a traceback.
        events_path.write_text(json.dumps(event) + "\n")
        result = run_cli(self.project, "status", "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["diagnostics"][0]["code"],
            "EVENT_HASH_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
