from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .errors import (
    GateBlockedError,
    InvalidStateError,
    NotInitializedError,
    ToolUnavailableError,
)
from .jsonutil import (
    atomic_write_json,
    atomic_write_text,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from .storage import EventStore, opaque_id, project_events, utc_now

EVIDENCE_TYPES = (
    "build",
    "test",
    "capture",
    "playtest",
    "technical",
    "other",
)
MANUAL_EVIDENCE_TYPES = tuple(kind for kind in EVIDENCE_TYPES if kind != "playtest")
MANUAL_TRUST_LEVELS = ("manually_imported", "human_attested")
RESULTS = ("passed", "failed", "observation")
GENERATED_DIRS = (
    ".loopforge",
    ".git",
    ".godot",
    "build",
    "dist",
    "artifacts",
    "captures",
)
HYPOTHESIS_FIELDS = (
    "intended_player",
    "platform",
    "player_fantasy",
    "core_verb",
    "moment_to_moment_loop",
    "hypothesis",
    "constraints",
    "non_goals",
    "cheapest_validation",
    "keep_signals",
    "kill_signals",
)
HYPOTHESIS_HEADINGS = {
    "intendedplayer": "intended_player",
    "player": "intended_player",
    "platform": "platform",
    "playerfantasy": "player_fantasy",
    "fantasy": "player_fantasy",
    "coreverb": "core_verb",
    "verb": "core_verb",
    "momenttomomentloop": "moment_to_moment_loop",
    "loop": "moment_to_moment_loop",
    "hypothesis": "hypothesis",
    "constraints": "constraints",
    "nongoals": "non_goals",
    "cheapestvalidation": "cheapest_validation",
    "validation": "cheapest_validation",
    "keepsignals": "keep_signals",
    "killsignals": "kill_signals",
}
TRANSITIONS = {
    "DISCOVERY": {"PROTOTYPING"},
    "PROTOTYPING": {"PLAYTEST_REQUIRED", "PROTOTYPE_DECISION"},
    "PLAYTEST_REQUIRED": {"PROTOTYPE_DECISION"},
    "PROTOTYPE_DECISION": {"KILLED", "PROTOTYPING", "VERTICAL_SLICE"},
}
PLAYTEST_REPORT_FIELDS = (
    "build_identity",
    "participant_context",
    "consent_status",
    "assistance_given",
    "raw_observations",
    "comprehension_time",
    "confusion_points",
    "failure_points",
    "abandonment_points",
    "strategies",
    "replay_behavior",
    "interpretation",
    "sensitive_data",
)
PLAYTEST_LIST_FIELDS = (
    "raw_observations",
    "confusion_points",
    "failure_points",
    "abandonment_points",
    "strategies",
)
PLAYTEST_TEXT_FIELDS = (
    "build_identity",
    "participant_context",
    "assistance_given",
    "comprehension_time",
    "replay_behavior",
    "interpretation",
    "sensitive_data",
)
PLAYTEST_CONSENT_VALUES = ("obtained", "not_required")
MAX_PLAYTEST_PROTOCOL_CHARS = 64 * 1024
MAX_PLAYTEST_ITEMS = 200
MAX_PLAYTEST_FIELD_CHARS = 4_000
MAX_DECISION_RATIONALE_CHARS = 8_000
MAX_DECISION_EVIDENCE = 64


class LoopforgeProject:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.store = EventStore(self.root)

    def init(self) -> dict[str, Any]:
        # Detection runs before the store is written, so the engine is
        # recorded at initialization rather than left null forever.
        detections = self.inspect()["engine_detections"]
        engine = detections[0]["engine"] if detections else None
        state, created = self.store.initialize(engine)
        result = {
            "created": created,
            "project_root": str(self.root),
            "state": state,
        }
        if created:
            result["committed_revision"] = state["revision"]
        else:
            result["observed_revision"] = state["revision"]
        return result

    def inspect(self) -> dict[str, Any]:
        detections: list[dict[str, Any]] = []
        if (self.root / "project.godot").is_file():
            detections.append(
                {
                    "engine": "godot",
                    "confidence": 1.0,
                    "evidence": ["project.godot"],
                }
            )
        if (self.root / "package.json").is_file():
            detections.append(
                {
                    "engine": "web",
                    "confidence": 0.6,
                    "evidence": ["package.json"],
                }
            )
        detections.sort(key=lambda item: (-item["confidence"], item["engine"]))

        executables = {}
        for name, candidates in {
            "git": ("git",),
            "godot": ("godot4", "godot"),
            "python": ("python3", "python"),
        }.items():
            executables[name] = next(
                (path for candidate in candidates if (path := shutil.which(candidate))),
                None,
            )

        initialized = self.store.initialized
        observed_revision = 0
        if initialized:
            state, _ = self.store.current_state()
            observed_revision = state["revision"]
        return {
            "project_root": str(self.root),
            "initialized": initialized,
            "observed_revision": observed_revision,
            "engine_detections": detections,
            "executables": executables,
        }

    def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        observed_revision = 0

        if self.store.initialized:
            validation = self.validate()
            observed_revision = validation["observed_revision"]
            if validation["valid"]:
                checks.append(
                    doctor_check(
                        "PROJECT_INTEGRITY", "passed", "Loopforge state is valid."
                    )
                )
            else:
                checks.append(
                    doctor_check(
                        "PROJECT_INTEGRITY",
                        "failed",
                        "Loopforge state or a referenced artifact is invalid.",
                    )
                )
                diagnostics.extend(validation["diagnostics"])
            self._append_run_diagnostics(checks, diagnostics)
        else:
            state_dir_entries = (
                list(self.store.state_dir.iterdir())
                if self.store.state_dir.is_dir()
                else []
            )
            if state_dir_entries:
                checks.append(
                    doctor_check(
                        "PROJECT_STATE",
                        "failed",
                        "The .loopforge directory contains partial "
                        "initialization state.",
                    )
                )
                diagnostics.append(
                    doctor_diagnostic(
                        "PROJECT_STATE_INCOMPLETE",
                        "Loopforge state is partially initialized.",
                        {"entries": sorted(path.name for path in state_dir_entries)},
                    )
                )
            else:
                checks.append(
                    doctor_check(
                        "PROJECT_STATE",
                        "warning",
                        "Loopforge is not initialized; run `loopforge init` "
                        "before recording work.",
                    )
                )

        engine = None
        project_file = self.root / "project.godot"
        if project_file.is_file():
            engine = "godot"
            executable = shutil.which("godot4") or shutil.which("godot")
            if executable is None:
                checks.append(
                    doctor_check(
                        "GODOT_EXECUTABLE",
                        "failed",
                        "A Godot project was detected but no Godot executable "
                        "is available.",
                    )
                )
                diagnostics.append(
                    doctor_diagnostic(
                        "REQUIRED_TOOL_UNAVAILABLE",
                        "Godot 4 was not found on PATH.",
                        {"expected": ["godot4", "godot"]},
                    )
                )
            else:
                version = self._godot_version(executable)
                major = godot_major_version(version)
                if version is None:
                    checks.append(
                        doctor_check(
                            "GODOT_VERSION",
                            "failed",
                            "The Godot executable did not report a version.",
                            {"executable": executable},
                        )
                    )
                    diagnostics.append(
                        doctor_diagnostic(
                            "GODOT_VERSION_UNAVAILABLE",
                            "The detected Godot executable could not be identified.",
                            {"executable": executable},
                        )
                    )
                elif major != 4:
                    checks.append(
                        doctor_check(
                            "GODOT_VERSION",
                            "failed",
                            "Loopforge's first engine adapter requires Godot 4.",
                            {"executable": executable, "version": version},
                        )
                    )
                    diagnostics.append(
                        doctor_diagnostic(
                            "GODOT_VERSION_UNSUPPORTED",
                            "The detected Godot version is not supported by "
                            "this adapter.",
                            {"version": version, "required_major": 4},
                        )
                    )
                else:
                    checks.append(
                        doctor_check(
                            "GODOT_VERSION",
                            "passed",
                            "A compatible Godot 4 executable is available.",
                            {"executable": executable, "version": version},
                        )
                    )
            self._append_godot_project_check(project_file, checks, diagnostics)
        else:
            checks.append(
                doctor_check(
                    "ENGINE_PROJECT",
                    "warning",
                    "No supported engine project was detected.",
                )
            )

        return {
            "healthy": not any(item["severity"] == "error" for item in diagnostics),
            "project_root": str(self.root),
            "engine": engine,
            "checks": checks,
            "observed_revision": observed_revision,
            "diagnostics": diagnostics,
        }

    def _append_godot_project_check(
        self,
        project_file: Path,
        checks: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        try:
            content = project_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            checks.append(
                doctor_check(
                    "GODOT_PROJECT_CONFIG",
                    "failed",
                    "project.godot cannot be read as UTF-8 text.",
                )
            )
            diagnostics.append(
                doctor_diagnostic(
                    "GODOT_PROJECT_UNREADABLE",
                    "The Godot project configuration cannot be read.",
                    {"path": str(project_file), "cause": str(exc)},
                )
            )
            return
        match = re.search(
            r'^\s*run/main_scene\s*=\s*[&]?"([^"]+)"', content, re.MULTILINE
        )
        if match is None:
            checks.append(
                doctor_check(
                    "GODOT_MAIN_SCENE",
                    "failed",
                    "The project has no configured main scene for startup checks.",
                )
            )
            diagnostics.append(
                doctor_diagnostic(
                    "GODOT_MAIN_SCENE_MISSING",
                    "Configure application/run/main_scene before running "
                    "startup evidence.",
                )
            )
            return
        main_scene = match.group(1)
        if main_scene.startswith("res://"):
            relative = main_scene.removeprefix("res://")
            scene_path = artifact_path(
                self.root,
                {"kind": "project-relative", "path": relative},
            )
            if scene_path is None or not scene_path.is_file():
                checks.append(
                    doctor_check(
                        "GODOT_MAIN_SCENE",
                        "failed",
                        "The configured main scene does not exist.",
                        {"main_scene": main_scene},
                    )
                )
                diagnostics.append(
                    doctor_diagnostic(
                        "GODOT_MAIN_SCENE_MISSING",
                        "The configured Godot main scene is unavailable.",
                        {"main_scene": main_scene},
                    )
                )
                return
        checks.append(
            doctor_check(
                "GODOT_MAIN_SCENE",
                "passed",
                "The project has a configured main scene.",
                {"main_scene": main_scene},
            )
        )

    def _append_run_diagnostics(
        self,
        checks: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        events = self.store.read_events()
        completed_run_ids = {
            event.get("run_id")
            for event in events
            if event["event_type"] == "run.completed" and event.get("run_id")
        }
        evidenced_run_ids = {
            event["payload"]["evidence"].get("run_id")
            for event in events
            if event["event_type"] == "evidence.registered"
            and event["payload"]["evidence"].get("run_id")
        }
        missing = sorted(completed_run_ids - evidenced_run_ids)
        status = "warning" if missing else "passed"
        message = (
            "Some completed runs have no registered evidence."
            if missing
            else "Every completed engine run has registered evidence."
        )
        checks.append(
            doctor_check("RUN_EVIDENCE", status, message, {"run_ids": missing})
        )
        if missing:
            diagnostics.append(
                doctor_diagnostic(
                    "RUN_EVIDENCE_MISSING",
                    "A completed run is not represented by an evidence event.",
                    {"run_ids": missing},
                    severity="warning",
                )
            )

        recorded_paths = {
            event["payload"]["run"].get("record_path")
            for event in events
            if event["event_type"] == "run.completed"
            and isinstance(event["payload"].get("run"), dict)
            and isinstance(event["payload"]["run"].get("record_path"), str)
        }
        run_dir = self.root / ".loopforge" / "runs"
        disk_paths = (
            {
                path.relative_to(self.root).as_posix()
                for path in run_dir.glob("*.json")
                if path.is_file()
            }
            if run_dir.is_dir()
            else set()
        )
        orphan_paths = sorted(disk_paths - recorded_paths)
        checks.append(
            doctor_check(
                "RUN_ARTIFACTS",
                "warning" if orphan_paths else "passed",
                "Uncommitted run artifacts were found."
                if orphan_paths
                else "No uncommitted run artifacts were found.",
                {"paths": orphan_paths},
            )
        )
        if orphan_paths:
            diagnostics.append(
                doctor_diagnostic(
                    "ORPHAN_RUN_ARTIFACT",
                    "A run artifact exists without a corresponding event.",
                    {"paths": orphan_paths},
                    severity="warning",
                )
            )

    def status(self) -> dict[str, Any]:
        if not self.store.initialized:
            return {
                "project_root": str(self.root),
                "initialized": False,
                "observed_revision": 0,
                "stage": "UNINITIALIZED",
                "snapshot_status": "missing",
                "next_allowed_actions": ["init"],
            }
        state, snapshot_status = self.store.current_state()
        return {
            "project_root": str(self.root),
            "initialized": True,
            # The id every event carries and every integrity check compares.
            # No command reported it except `history`, so the id a surface
            # showed the user was one they could not look up anywhere.
            "project_id": state["project_id"],
            "observed_revision": state["revision"],
            "stage": state["stage"],
            "active_experiment": state["active_experiment"],
            "evidence_count": state["evidence_count"],
            "snapshot_status": snapshot_status,
            "claims": self.quality_claims(state),
            "next_allowed_actions": self._next_actions(state["stage"], snapshot_status),
        }

    def validate(self) -> dict[str, Any]:
        if not self.store.initialized:
            raise NotInitializedError(str(self.root))
        config = self.store.read_project_config()
        events = self.store.read_events()
        state = project_events(events)
        _, snapshot_status = self.store.current_state()
        diagnostics: list[dict[str, Any]] = []
        if snapshot_status != "current":
            diagnostics.append(
                {
                    "code": "STATE_SNAPSHOT_NOT_CURRENT",
                    "severity": "error",
                    "message": "The derived state snapshot must be reconciled.",
                    "details": {"snapshot_status": snapshot_status},
                }
            )
        if config["project_id"] != state["project_id"]:
            diagnostics.append(
                {
                    "code": "PROJECT_ID_MISMATCH",
                    "severity": "error",
                    "message": "Project configuration and event history disagree.",
                }
            )
        diagnostics.extend(self._record_integrity_diagnostics(events))
        return {
            "valid": not diagnostics,
            "observed_revision": state["revision"],
            "event_count": len(events),
            "snapshot_status": snapshot_status,
            "diagnostics": diagnostics,
        }

    def quality_claims(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        if state is None:
            state, _ = self.store.current_state()
        evidence = self._evidence_by_id()
        current_source = self._source_identity(self._registered_artifact_paths())
        scoped: dict[str, list[dict[str, Any]]] = {}
        stale: dict[str, list[dict[str, Any]]] = {}
        experiment_id = state["active_experiment"]["experiment_id"]
        hypothesis_revision = state["active_experiment"]["hypothesis_revision"]
        for record in evidence.values():
            if record.get("revoked"):
                continue
            subject = record.get("subject", {})
            if (
                subject.get("experiment_id") != experiment_id
                or subject.get("hypothesis_revision") != hypothesis_revision
            ):
                continue
            target = (
                scoped if record.get("source_identity") == current_source else stale
            )
            target.setdefault(record.get("type", "other"), []).append(record)

        claims: dict[str, dict[str, Any]] = {}
        build = latest_record(scoped.get("build", []))
        test = latest_record(scoped.get("test", []))
        technical_records = [record for record in (build, test) if record]
        if any(
            not self._evidence_eligible_for_claim(record)
            for record in technical_records
        ):
            claims["TECHNICALLY_VALIDATED"] = claim("unknown", technical_records)
        elif (
            build
            and test
            and build.get("result") == "passed"
            and test.get("result") == "passed"
        ):
            claims["TECHNICALLY_VALIDATED"] = claim("satisfied", technical_records)
        elif any(record.get("result") == "failed" for record in technical_records):
            claims["TECHNICALLY_VALIDATED"] = claim("failed", technical_records)
        elif stale.get("build") or stale.get("test"):
            claims["TECHNICALLY_VALIDATED"] = claim(
                "stale", stale.get("build", []) + stale.get("test", [])
            )
        else:
            claims["TECHNICALLY_VALIDATED"] = claim("unknown", [])

        capture = latest_record(scoped.get("capture", []))
        if capture:
            capture_status = (
                "satisfied" if self._evidence_eligible_for_claim(capture) else "unknown"
            )
            claims["VISUALLY_REVIEWED"] = claim(capture_status, [capture])
        elif stale.get("capture"):
            claims["VISUALLY_REVIEWED"] = claim("stale", stale["capture"])
        else:
            claims["VISUALLY_REVIEWED"] = claim("unknown", [])
        playtest = latest_record(scoped.get("playtest", []))
        valid_playtest = None
        if playtest:
            if self._evidence_eligible_for_claim(playtest):
                valid_playtest = playtest
            claims["HUMAN_PLAYTESTED"] = claim(
                "satisfied" if valid_playtest else "unknown", [playtest]
            )
        elif stale.get("playtest"):
            claims["HUMAN_PLAYTESTED"] = claim("stale", stale["playtest"])
        else:
            claims["HUMAN_PLAYTESTED"] = claim("unknown", [])
        decision = self._latest_decision(experiment_id, hypothesis_revision)
        if decision and decision.get("decision") == "keep" and valid_playtest:
            claims["FUN_HYPOTHESIS_SUPPORTED"] = claim(
                "satisfied", [valid_playtest], [decision]
            )
        elif decision and decision.get("decision") == "kill":
            claims["FUN_HYPOTHESIS_SUPPORTED"] = claim("failed", [], [decision])
        else:
            claims["FUN_HYPOTHESIS_SUPPORTED"] = claim("unknown", [])
        claims["RELEASE_APPROVED"] = claim("unknown", [])
        return claims

    def _record_integrity_diagnostics(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        evidence_records = self._evidence_by_id()
        evidence_ids = set(evidence_records)
        registered_before: set[str] = set()
        for event in events:
            payload = event["payload"]
            if event["event_type"] == "evidence.registered":
                record = payload["evidence"]
                registered_before.add(str(record.get("evidence_id") or ""))
                if evidence_records.get(record.get("evidence_id"), {}).get("revoked"):
                    continue
                artifact = record.get("artifact", {})
                path = artifact_path(self.root, artifact)
                if path is None or not path.is_file():
                    diagnostics.append(
                        diagnostic(
                            "EVIDENCE_ARTIFACT_MISSING",
                            "Referenced evidence artifact is unavailable.",
                            event["event_id"],
                        )
                    )
                elif not checksum_matches(path, artifact.get("checksum")):
                    diagnostics.append(
                        diagnostic(
                            "EVIDENCE_CHECKSUM_INVALID",
                            "Referenced evidence checksum does not match the file.",
                            event["event_id"],
                        )
                    )
            elif event["event_type"] == "evidence.revoked":
                identifier = str(payload.get("evidence_id") or "")
                record = evidence_records.get(identifier)
                if identifier not in registered_before or record is None:
                    diagnostics.append(
                        diagnostic(
                            "EVIDENCE_REVOCATION_UNKNOWN",
                            "Evidence revocation references an unknown record.",
                            event["event_id"],
                            {"evidence_id": identifier},
                        )
                    )
                elif record.get("type") != "playtest":
                    diagnostics.append(
                        diagnostic(
                            "EVIDENCE_REVOCATION_TYPE_INVALID",
                            "Only external playtest evidence may be consent-revoked.",
                            event["event_id"],
                            {"evidence_id": identifier},
                        )
                    )
            elif event["event_type"] == "hypothesis.created":
                record = payload["hypothesis"]
                if not artifact_checksum_matches(
                    self.root,
                    record.get("content_path"),
                    record.get("content_checksum"),
                ):
                    diagnostics.append(
                        diagnostic(
                            "HYPOTHESIS_ARTIFACT_INVALID",
                            "Hypothesis content is missing or changed.",
                            event["event_id"],
                        )
                    )
            elif event["event_type"] == "playtest.protocol.created":
                record = payload["protocol"]
                if not artifact_checksum_matches(
                    self.root,
                    record.get("path"),
                    record.get("checksum"),
                ):
                    diagnostics.append(
                        diagnostic(
                            "PLAYTEST_PROTOCOL_INVALID",
                            "Playtest protocol is missing or changed.",
                            event["event_id"],
                        )
                    )
            elif event["event_type"] == "decision.recorded":
                cited = payload["decision"].get("evidence_ids", [])
                missing = [
                    evidence_id
                    for evidence_id in cited
                    if evidence_id not in evidence_ids
                ]
                if missing:
                    diagnostics.append(
                        diagnostic(
                            "DECISION_EVIDENCE_UNKNOWN",
                            "Decision references evidence that is not present "
                            "in history.",
                            event["event_id"],
                            {"missing": missing},
                        )
                    )
                revised_hypothesis = payload.get("hypothesis")
                if revised_hypothesis and not artifact_checksum_matches(
                    self.root,
                    revised_hypothesis.get("content_path"),
                    revised_hypothesis.get("content_checksum"),
                ):
                    diagnostics.append(
                        diagnostic(
                            "HYPOTHESIS_ARTIFACT_INVALID",
                            "Revised hypothesis content is missing or changed.",
                            event["event_id"],
                        )
                    )
        return diagnostics

    def history(self) -> dict[str, Any]:
        events = self.store.read_events()
        return {
            "observed_revision": events[-1]["revision"] if events else 0,
            "events": events,
        }

    def reconcile(self, apply: bool) -> dict[str, Any]:
        def require_intact_history(
            events: list[dict[str, Any]], projected: dict[str, Any]
        ) -> None:
            config = self.store.read_project_config()
            if config["project_id"] != projected["project_id"]:
                raise InvalidStateError(
                    "Project configuration and event history disagree.",
                    "PROJECT_ID_MISMATCH",
                )
            diagnostics = self._record_integrity_diagnostics(events)
            if diagnostics:
                raise InvalidStateError(
                    "Referenced artifacts are invalid; reconcile cannot repair them.",
                    "RECONCILE_INTEGRITY_FAILED",
                    {"diagnostics": diagnostics},
                )

        return self.store.reconcile(apply, require_intact_history)

    def add_evidence(
        self,
        evidence_type: str,
        file: Path,
        trust_level: str,
        result: str,
        expected_revision: int | None,
        producer: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if evidence_type == "playtest":
            raise InvalidStateError(
                "External playtest evidence must be imported through a "
                "validated report.",
                "PLAYTEST_IMPORT_REQUIRED",
                {"remediation": "Use playtest create, then playtest import."},
            )
        return self._register_evidence(
            evidence_type,
            file,
            trust_level,
            result,
            expected_revision,
            producer,
            metadata,
        )

    def _register_evidence(
        self,
        evidence_type: str,
        file: Path,
        trust_level: str,
        result: str,
        expected_revision: int | None,
        producer: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if evidence_type not in EVIDENCE_TYPES:
            raise InvalidStateError(
                f"Unsupported evidence type: {evidence_type}",
                "EVIDENCE_TYPE_INVALID",
                {"allowed": list(EVIDENCE_TYPES)},
            )
        if trust_level not in MANUAL_TRUST_LEVELS:
            raise InvalidStateError(
                f"Unsupported manual trust level: {trust_level}",
                "EVIDENCE_TRUST_LEVEL_INVALID",
                {"allowed": list(MANUAL_TRUST_LEVELS)},
            )
        if result not in RESULTS:
            raise InvalidStateError(
                f"Unsupported evidence result: {result}",
                "EVIDENCE_RESULT_INVALID",
                {"allowed": list(RESULTS)},
            )
        absolute_file = file.expanduser().resolve()
        if not absolute_file.is_file():
            raise InvalidStateError(
                "Evidence path must reference an existing regular file.",
                "EVIDENCE_FILE_MISSING",
                {"path": str(absolute_file)},
            )

        current_state, _ = self.store.current_state()
        excluded_paths = self._registered_artifact_paths()
        excluded_paths.add(absolute_file)
        source_identity = self._source_identity(excluded_paths)
        try:
            relative = absolute_file.relative_to(self.root)
            artifact_path = {
                "kind": "project-relative",
                "path": relative.as_posix(),
            }
        except ValueError:
            artifact_path = {
                "kind": "absolute",
                "path": str(absolute_file),
            }

        record = {
            "schema_version": 1,
            "evidence_id": opaque_id("evd"),
            "type": evidence_type,
            "result": result,
            "created_at": utc_now(),
            "trust_level": trust_level,
            "producer": producer or "local-user",
            "subject": {
                "experiment_id": current_state["active_experiment"]["experiment_id"],
                "hypothesis_revision": current_state["active_experiment"][
                    "hypothesis_revision"
                ],
            },
            "source_identity": source_identity,
            "artifact": {
                **artifact_path,
                "checksum": sha256_file(absolute_file),
                "size": absolute_file.stat().st_size,
            },
        }
        if metadata:
            record["metadata"] = metadata
        event, new_state = self.store.commit(
            "evidence.registered",
            {"evidence": record},
            current_state["revision"]
            if expected_revision is None
            else expected_revision,
        )
        record["registration_revision"] = event["revision"]
        return {
            "evidence": record,
            "committed_revision": new_state["revision"],
        }

    def list_evidence(self) -> dict[str, Any]:
        events = self.store.read_events()
        by_id = self._evidence_by_id()
        records = sorted(
            by_id.values(), key=lambda record: record["registration_revision"]
        )
        return {
            "observed_revision": events[-1]["revision"],
            "evidence": records,
        }

    def revoke_playtest_evidence(
        self,
        evidence_id: str,
        reason: str,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        identifier = str(evidence_id or "").strip()
        rationale = str(reason or "").strip()
        if not identifier:
            raise InvalidStateError(
                "A playtest evidence ID is required.",
                "PLAYTEST_EVIDENCE_MISSING",
            )
        if not rationale:
            raise InvalidStateError(
                "A consent-revocation reason is required.",
                "PLAYTEST_REVOCATION_REASON_MISSING",
            )
        if len(rationale) > MAX_PLAYTEST_FIELD_CHARS:
            raise InvalidStateError(
                "The consent-revocation reason is too long.",
                "PLAYTEST_REVOCATION_REASON_INVALID",
                {"max_characters": MAX_PLAYTEST_FIELD_CHARS},
            )
        records = self._evidence_by_id()
        record = records.get(identifier)
        if record is None or record.get("type") != "playtest":
            raise InvalidStateError(
                "The requested external playtest evidence does not exist.",
                "PLAYTEST_EVIDENCE_UNKNOWN",
                {"evidence_id": identifier},
            )
        if record.get("revoked"):
            state, _ = self.store.current_state()
            deleted, deletion_error = self._delete_stored_playtest_report(record)
            return {
                "evidence_id": identifier,
                "revoked": True,
                "already_revoked": True,
                "artifact_deleted": deleted,
                "deletion_error": deletion_error,
                "committed_revision": state["revision"],
            }
        state, _ = self.store.current_state()
        revoked_at = utc_now()
        event, final_state = self.store.commit(
            "evidence.revoked",
            {
                "evidence_id": identifier,
                "reason": rationale,
                "revoked_at": revoked_at,
            },
            state["revision"] if expected_revision is None else expected_revision,
        )
        deleted, deletion_error = self._delete_stored_playtest_report(record)
        return {
            "evidence_id": identifier,
            "revocation_event_id": event["event_id"],
            "revoked": True,
            "already_revoked": False,
            "artifact_deleted": deleted,
            "deletion_error": deletion_error,
            "committed_revision": final_state["revision"],
        }

    def _delete_stored_playtest_report(
        self, record: dict[str, Any]
    ) -> tuple[bool, str | None]:
        artifact = record.get("artifact", {})
        path = artifact_path(self.root, artifact)
        if (
            path is None
            or artifact.get("kind") != "project-relative"
            or not path.is_relative_to(self.store.state_dir / "playtests")
        ):
            return False, "The report is not in Loopforge's managed playtest store."
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            return False, str(exc)
        return True, None

    def _evidence_artifact_exists(self, record: dict[str, Any]) -> bool:
        path = artifact_path(self.root, record.get("artifact", {}))
        return path is not None and path.is_file()

    def run_engine(
        self,
        operation: str,
        expected_revision: int | None,
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        if operation not in {"build", "test"}:
            raise InvalidStateError(
                f"Unsupported engine operation: {operation}",
                "ENGINE_OPERATION_INVALID",
                {"allowed": ["build", "test"]},
            )
        if not (self.root / "project.godot").is_file():
            raise InvalidStateError(
                "The Godot adapter requires project.godot.",
                "ENGINE_PROJECT_NOT_DETECTED",
            )
        executable = shutil.which("godot4") or shutil.which("godot")
        if executable is None:
            raise ToolUnavailableError(
                "Godot executable was not found on PATH.",
                {"operation": operation, "expected": ["godot4", "godot"]},
            )
        adapter_version = self._godot_version(executable)
        if godot_major_version(adapter_version) != 4:
            raise InvalidStateError(
                "The Godot adapter requires a Godot 4 executable.",
                "GODOT_VERSION_UNSUPPORTED",
                {"executable": executable, "version": adapter_version},
            )

        state, _ = self.store.current_state()
        run_id = opaque_id("run")
        run_dir = self.root / ".loopforge" / "runs"
        run_path = run_dir / f"{run_id}.json"
        command = [executable, "--headless", "--path", str(self.root)]
        if operation == "build":
            command.extend(["--editor", "--quit"])
        else:
            command.append("--quit")
        started_at = utc_now()
        status = "completed"
        exit_code: int | None = None
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            engine_errors = godot_error_lines(stdout, stderr)
            if exit_code != 0 or engine_errors:
                status = "failed"
        except subprocess.TimeoutExpired as exc:
            status = "interrupted"
            timed_out = True
            stdout = _decode_process_output(exc.stdout)
            stderr = _decode_process_output(exc.stderr)
            engine_errors = godot_error_lines(stdout, stderr)

        run_record = {
            "schema_version": 1,
            "run_id": run_id,
            "operation": operation,
            "adapter": "godot",
            "adapter_version": adapter_version,
            "command": command,
            "cwd": str(self.root),
            "started_at": started_at,
            "finished_at": utc_now(),
            "status": status,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout": stdout,
            "stderr": stderr,
            "engine_errors": engine_errors,
        }
        atomic_write_json(run_path, run_record)
        run_event, _ = self.store.commit(
            "run.completed",
            {
                "run": {
                    **run_record,
                    "record_path": str(run_path.relative_to(self.root)),
                }
            },
            state["revision"] if expected_revision is None else expected_revision,
            run_id=run_id,
        )
        evidence = {
            "schema_version": 1,
            "evidence_id": opaque_id("evd"),
            "type": "build" if operation == "build" else "test",
            "result": "passed"
            if status == "completed" and exit_code == 0
            else "failed",
            "created_at": utc_now(),
            "trust_level": "tool_generated",
            "producer": "loopforge.adapter.godot",
            "subject": {
                "experiment_id": state["active_experiment"]["experiment_id"],
                "hypothesis_revision": state["active_experiment"][
                    "hypothesis_revision"
                ],
            },
            "source_identity": self._source_identity(
                self._registered_artifact_paths() | {run_path}
            ),
            "artifact": {
                "kind": "project-relative",
                "path": run_path.relative_to(self.root).as_posix(),
                "checksum": sha256_file(run_path),
                "size": run_path.stat().st_size,
            },
            "run_id": run_id,
        }
        evidence_event, new_state = self.store.commit(
            "evidence.registered",
            {"evidence": evidence},
            run_event["revision"],
            run_id=run_id,
        )
        evidence["registration_revision"] = evidence_event["revision"]
        return {
            "run": run_record,
            "evidence": evidence,
            "committed_revision": new_state["revision"],
        }

    def capture_screenshot(
        self,
        file: Path,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        candidate = file.expanduser().resolve()
        if candidate.is_file() and not valid_capture_image(candidate):
            raise InvalidStateError(
                "The selected capture has no valid PNG, JPEG, or WebP header.",
                "CAPTURE_FORMAT_INVALID",
                {"path": str(candidate)},
            )
        return self.add_evidence(
            "capture",
            file,
            "manually_imported",
            "observation",
            expected_revision,
            "local-screenshot-import",
        )

    def create_playtest_protocol(
        self,
        file: Path,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        state, _ = self.store.current_state()
        if state["stage"] != "PLAYTEST_REQUIRED":
            raise InvalidStateError(
                "A playtest protocol can only be created while playtesting "
                "is required.",
                "PLAYTEST_STAGE_INVALID",
                {"stage": state["stage"]},
            )
        source = file.expanduser().resolve()
        if not source.is_file():
            raise InvalidStateError(
                "The playtest protocol file does not exist.",
                "PLAYTEST_PROTOCOL_MISSING",
                {"path": str(source)},
            )
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InvalidStateError(
                "The playtest protocol cannot be read as UTF-8 text.",
                "PLAYTEST_PROTOCOL_INVALID",
                {"path": str(source), "cause": str(exc)},
            ) from exc
        if not content.strip():
            raise InvalidStateError(
                "The playtest protocol must not be empty.",
                "PLAYTEST_PROTOCOL_INVALID",
            )
        if len(content) > MAX_PLAYTEST_PROTOCOL_CHARS:
            raise InvalidStateError(
                "The playtest protocol is too large.",
                "PLAYTEST_PROTOCOL_INVALID",
                {"max_characters": MAX_PLAYTEST_PROTOCOL_CHARS},
            )
        source_identity = self._source_identity(self._registered_artifact_paths())
        protocol_id = opaque_id("plt")
        relative_path = Path(".loopforge") / "playtests" / f"{protocol_id}-protocol.md"
        stored_path = self.root / relative_path
        atomic_write_text(stored_path, content)
        protocol = {
            "schema_version": 1,
            "protocol_id": protocol_id,
            "experiment_id": state["active_experiment"]["experiment_id"],
            "hypothesis_revision": state["active_experiment"]["hypothesis_revision"],
            "path": relative_path.as_posix(),
            "checksum": sha256_file(stored_path),
            "source_identity": source_identity,
            "build_identity": playtest_build_identity(source_identity),
            "created_at": utc_now(),
        }
        try:
            event, new_state = self.store.commit(
                "playtest.protocol.created",
                {"protocol": protocol},
                state["revision"] if expected_revision is None else expected_revision,
            )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        protocol["registration_revision"] = event["revision"]
        return {"protocol": protocol, "committed_revision": new_state["revision"]}

    def import_playtest(
        self,
        file: Path,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        state, _ = self.store.current_state()
        if state["stage"] != "PLAYTEST_REQUIRED":
            raise InvalidStateError(
                "A playtest report can only be imported while playtesting is required.",
                "PLAYTEST_STAGE_INVALID",
                {"stage": state["stage"]},
            )
        protocol = self._latest_protocol(state)
        if protocol is None:
            raise InvalidStateError(
                "Create a playtest protocol before importing a report.",
                "PLAYTEST_PROTOCOL_MISSING",
            )
        source = file.expanduser().resolve()
        if not source.is_file():
            raise InvalidStateError(
                "The playtest report file does not exist.",
                "PLAYTEST_REPORT_MISSING",
                {"path": str(source)},
            )
        try:
            report = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidStateError(
                "The playtest report is not valid JSON.",
                "PLAYTEST_REPORT_INVALID",
                {"cause": str(exc)},
            ) from exc
        report = normalize_playtest_report(report)
        current_source_identity = self._source_identity(
            self._registered_artifact_paths()
        )
        protocol_source_identity = protocol.get("source_identity")
        if (
            protocol_source_identity is not None
            and protocol_source_identity != current_source_identity
        ):
            raise InvalidStateError(
                "The project changed after this playtest protocol was recorded.",
                "PLAYTEST_BUILD_STALE",
                {
                    "protocol_build_identity": protocol.get("build_identity"),
                    "current_build_identity": playtest_build_identity(
                        current_source_identity
                    ),
                },
            )
        expected_build_identity = protocol.get("build_identity") or (
            playtest_build_identity(current_source_identity)
        )
        if report["build_identity"] != expected_build_identity:
            raise InvalidStateError(
                "The playtest report does not identify the build bound to "
                "its protocol.",
                "PLAYTEST_BUILD_MISMATCH",
                {
                    "expected": expected_build_identity,
                    "reported": report["build_identity"],
                },
            )
        report_id = opaque_id("rpt")
        relative_path = Path(".loopforge") / "playtests" / f"{report_id}.json"
        stored_path = self.root / relative_path
        atomic_write_json(stored_path, report)
        try:
            result = self._register_evidence(
                "playtest",
                stored_path,
                "human_attested",
                "observation",
                state["revision"] if expected_revision is None else expected_revision,
                "local-playtest-import",
                {
                    "protocol_id": protocol["protocol_id"],
                    "report_id": report_id,
                    "report_fields": list(PLAYTEST_REPORT_FIELDS),
                },
            )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        result["report_id"] = report_id
        return result

    def playtest_build_identity(self) -> str:
        """Stable public token for the source a protocol will bind to."""
        return playtest_build_identity(
            self._source_identity(self._registered_artifact_paths())
        )

    def decide(
        self,
        decision: str,
        evidence_ids: list[str],
        expected_revision: int | None,
        approver_id: str | None,
        approver_name: str | None,
        rationale: str | None,
        revised_hypothesis: Path | None = None,
    ) -> dict[str, Any]:
        if decision not in {"keep", "kill", "refactor"}:
            raise InvalidStateError(
                "Unsupported prototype decision.", "DECISION_INVALID"
            )
        state, _ = self.store.current_state()
        if state["stage"] != "PROTOTYPE_DECISION":
            raise InvalidStateError(
                "A prototype decision can only be recorded from PROTOTYPE_DECISION.",
                "DECISION_STAGE_INVALID",
                {"stage": state["stage"]},
            )
        evidence_ids = [str(item).strip() for item in evidence_ids]
        if not evidence_ids or any(not item for item in evidence_ids):
            raise InvalidStateError(
                "At least one evidence ID is required.", "DECISION_EVIDENCE_MISSING"
            )
        if len(evidence_ids) > MAX_DECISION_EVIDENCE:
            raise InvalidStateError(
                "The decision cites too many evidence records.",
                "DECISION_EVIDENCE_INVALID",
                {"max_items": MAX_DECISION_EVIDENCE},
            )
        approver_id = str(approver_id or "").strip()
        approver_name = str(approver_name or "").strip()
        rationale = str(rationale or "").strip()
        if not all((approver_id, approver_name, rationale)):
            raise InvalidStateError(
                "Approver ID, approver name, and rationale are required.",
                "APPROVAL_INCOMPLETE",
            )
        if len(rationale) > MAX_DECISION_RATIONALE_CHARS:
            raise InvalidStateError(
                "The decision rationale is too long.",
                "DECISION_RATIONALE_INVALID",
                {"max_characters": MAX_DECISION_RATIONALE_CHARS},
            )
        records = self._evidence_by_id()
        missing = [
            evidence_id for evidence_id in evidence_ids if evidence_id not in records
        ]
        if missing:
            raise InvalidStateError(
                "The decision cites unknown evidence IDs.",
                "DECISION_EVIDENCE_UNKNOWN",
                {"missing": missing},
            )
        revoked = [
            evidence_id
            for evidence_id in evidence_ids
            if records[evidence_id].get("revoked")
        ]
        if revoked:
            raise InvalidStateError(
                "The decision cites revoked evidence.",
                "DECISION_EVIDENCE_REVOKED",
                {"evidence_ids": revoked},
            )
        wrong_subject = [
            evidence_id
            for evidence_id in evidence_ids
            if records[evidence_id].get("subject", {}).get("experiment_id")
            != state["active_experiment"]["experiment_id"]
            or records[evidence_id].get("subject", {}).get("hypothesis_revision")
            != state["active_experiment"]["hypothesis_revision"]
        ]
        if wrong_subject:
            raise InvalidStateError(
                "The decision cites evidence from a different experiment or "
                "hypothesis revision.",
                "DECISION_EVIDENCE_OUT_OF_SCOPE",
                {"evidence_ids": wrong_subject},
            )
        invalid_artifacts: list[str] = []
        for evidence_id in evidence_ids:
            artifact = records[evidence_id].get("artifact", {})
            path = artifact_path(self.root, artifact)
            if (
                path is None
                or not path.is_file()
                or not checksum_matches(path, artifact.get("checksum"))
                or (
                    records[evidence_id].get("type") == "playtest"
                    and not self._validated_playtest_evidence(records[evidence_id])
                )
            ):
                invalid_artifacts.append(evidence_id)
        if invalid_artifacts:
            raise InvalidStateError(
                "The decision cites missing or modified evidence artifacts.",
                "DECISION_EVIDENCE_INVALID",
                {"evidence_ids": invalid_artifacts},
            )
        playtest = (
            self._latest_evidence(state, "playtest") if decision == "keep" else None
        )
        if decision == "keep" and (
            playtest is None or not self._evidence_eligible_for_claim(playtest)
        ):
            raise GateBlockedError(
                "Keep requires an applicable external playtest report.",
                {"requirement": "PLAYTEST_REPORT"},
            )
        if decision == "keep":
            entry = self._prototype_decision_entry()
            if entry and entry.get("from") == "PROTOTYPING":
                raise GateBlockedError(
                    "An early technical or scope decision cannot keep the prototype.",
                    {"requirement": "EXTERNAL_PLAYTEST_PATH_REQUIRED"},
                )
            if playtest["evidence_id"] not in evidence_ids:
                raise InvalidStateError(
                    "A keep decision must cite the applicable playtest report.",
                    "DECISION_PLAYTEST_NOT_CITED",
                )
        if decision == "refactor":
            if revised_hypothesis is None:
                raise InvalidStateError(
                    "Refactor requires --file with a revised hypothesis.",
                    "REVISED_HYPOTHESIS_MISSING",
                )
            revised_source = revised_hypothesis.expanduser().resolve()
            if not revised_source.is_file():
                raise InvalidStateError(
                    "The revised hypothesis file does not exist.",
                    "REVISED_HYPOTHESIS_MISSING",
                    {"path": str(revised_source)},
                )
            try:
                revised_content = revised_source.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise InvalidStateError(
                    "The revised hypothesis cannot be read as UTF-8 text.",
                    "HYPOTHESIS_FILE_UNREADABLE",
                    {"path": str(revised_source), "cause": str(exc)},
                ) from exc
            revised_fields = parse_hypothesis(
                revised_content, revised_source.suffix.lower()
            )
        else:
            revised_source = None
            revised_content = None
            revised_fields = None

        approval = {
            "approver_id": approver_id,
            "approver_display_name": approver_name,
            "identity_source": "local-declaration",
            "rationale": rationale,
            "rationale_checksum": sha256_bytes(
                canonical_json_bytes({"rationale": rationale})
            ),
            "approved_at": utc_now(),
        }
        decision_record = {
            "decision": decision,
            "experiment_id": state["active_experiment"]["experiment_id"],
            "hypothesis_revision": state["active_experiment"]["hypothesis_revision"],
            "evidence_ids": evidence_ids,
            "approval": approval,
            "created_at": utc_now(),
        }
        target = {
            "keep": "VERTICAL_SLICE",
            "kill": "KILLED",
            "refactor": "PROTOTYPING",
        }[decision]
        payload: dict[str, Any] = {
            "decision": decision_record,
            "transition": {
                "from": "PROTOTYPE_DECISION",
                "to": target,
                "reason": decision,
            },
        }
        stored_path: Path | None = None
        if decision == "refactor":
            hypothesis_id = opaque_id("hyp")
            relative_path = Path(".loopforge") / "hypotheses" / f"{hypothesis_id}.md"
            stored_path = self.root / relative_path
            atomic_write_text(stored_path, revised_content)
            payload["hypothesis"] = {
                "hypothesis_id": hypothesis_id,
                "revision": (state["active_experiment"]["hypothesis_revision"] or 0)
                + 1,
                "experiment_id": state["active_experiment"]["experiment_id"],
                "fields": revised_fields,
                "content_path": relative_path.as_posix(),
                "content_checksum": sha256_file(stored_path),
                "approval": approval,
                "created_at": utc_now(),
            }
        try:
            decision_event, final_state = self.store.commit(
                "decision.recorded",
                payload,
                state["revision"] if expected_revision is None else expected_revision,
            )
        except Exception:
            if stored_path is not None:
                stored_path.unlink(missing_ok=True)
            raise
        return {
            "decision": decision_record,
            "decision_event_id": decision_event["event_id"],
            "committed_revision": final_state["revision"],
            "state": final_state,
        }

    @staticmethod
    def _godot_version(executable: str) -> str | None:
        try:
            result = subprocess.run(
                [executable, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return (result.stdout or result.stderr).strip() or None

    def create_hypothesis(
        self,
        file: Path,
        expected_revision: int | None,
        approver_id: str | None,
        approver_name: str | None,
        rationale: str | None,
        allow_decision_stage: bool = False,
    ) -> dict[str, Any]:
        state, _ = self.store.current_state()
        if state["stage"] != "DISCOVERY" and not (
            allow_decision_stage and state["stage"] == "PROTOTYPE_DECISION"
        ):
            raise InvalidStateError(
                "A hypothesis can only be created during discovery.",
                "HYPOTHESIS_STAGE_INVALID",
                {"stage": state["stage"]},
            )
        content_path = file.expanduser().resolve()
        if not content_path.is_file():
            raise InvalidStateError(
                "The hypothesis file does not exist.",
                "HYPOTHESIS_FILE_MISSING",
                {"path": str(content_path)},
            )
        try:
            content = content_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InvalidStateError(
                "The hypothesis file cannot be read.",
                "HYPOTHESIS_FILE_UNREADABLE",
                {"path": str(content_path), "cause": str(exc)},
            ) from exc
        fields = parse_hypothesis(content, content_path.suffix.lower())
        approval = None
        if approver_id or approver_name or rationale:
            if not all(
                str(value or "").strip()
                for value in (approver_id, approver_name, rationale)
            ):
                raise InvalidStateError(
                    "Approver ID, approver name, and rationale must be supplied "
                    "together.",
                    "APPROVAL_INCOMPLETE",
                )
            approval = {
                "approver_id": approver_id,
                "approver_display_name": approver_name,
                "identity_source": "local-declaration",
                "rationale": rationale,
                "rationale_checksum": sha256_bytes(
                    canonical_json_bytes({"rationale": rationale})
                ),
                "approved_at": utc_now(),
            }
        hypothesis_id = opaque_id("hyp")
        revision = (state["active_experiment"]["hypothesis_revision"] or 0) + 1
        relative_path = Path(".loopforge") / "hypotheses" / f"{hypothesis_id}.md"
        stored_path = self.root / relative_path
        atomic_write_text(stored_path, content)
        record = {
            "hypothesis_id": hypothesis_id,
            "revision": revision,
            "experiment_id": state["active_experiment"]["experiment_id"],
            "fields": fields,
            "content_path": relative_path.as_posix(),
            "content_checksum": sha256_file(stored_path),
            "approval": approval,
            "created_at": utc_now(),
        }
        try:
            event, new_state = self.store.commit(
                "hypothesis.created",
                {"hypothesis": record},
                state["revision"] if expected_revision is None else expected_revision,
            )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        record["registration_revision"] = event["revision"]
        return {
            "hypothesis": record,
            "committed_revision": new_state["revision"],
        }

    def show_hypothesis(self) -> dict[str, Any]:
        state, _ = self.store.current_state()
        hypothesis_id = state["active_experiment"].get("hypothesis_id")
        if not hypothesis_id:
            raise InvalidStateError(
                "The active experiment has no hypothesis.",
                "HYPOTHESIS_MISSING",
            )
        for event in reversed(self.store.read_events()):
            record = hypothesis_from_event(event)
            if record is None:
                continue
            if record.get("hypothesis_id") == hypothesis_id:
                result = dict(record)
                result["registration_revision"] = event["revision"]
                return {
                    "observed_revision": state["revision"],
                    "hypothesis": result,
                }
        raise InvalidStateError(
            "The active hypothesis is not present in event history.",
            "HYPOTHESIS_RECORD_MISSING",
        )

    def gate_check(
        self,
        target_stage: str,
        reason: str | None = None,
        approver_id: str | None = None,
        approver_name: str | None = None,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        target_stage = target_stage.upper()
        state, snapshot_status = self.store.current_state()
        requirements: list[dict[str, Any]] = []
        human_confirmed = all(
            isinstance(value, str) and bool(value.strip())
            for value in (approver_id, approver_name, rationale)
        )
        if snapshot_status != "current":
            requirements.append(
                requirement(
                    "STATE_SNAPSHOT_CURRENT",
                    "invalid",
                    "Reconcile the derived state snapshot before advancing.",
                )
            )
        current_stage = state["stage"]
        if target_stage not in TRANSITIONS.get(current_stage, set()):
            requirements.append(
                requirement(
                    "TRANSITION_ALLOWED",
                    "invalid",
                    f"No transition is defined from {current_stage} to {target_stage}.",
                )
            )
        elif current_stage == "DISCOVERY" and target_stage == "PROTOTYPING":
            hypothesis = self._active_hypothesis(state)
            requirements.extend(
                [
                    requirement(
                        "HYPOTHESIS_PRESENT",
                        "satisfied" if hypothesis else "missing",
                        "An active hypothesis record is required.",
                    ),
                    requirement(
                        "HYPOTHESIS_COMPLETE",
                        "satisfied"
                        if hypothesis
                        and all(
                            hypothesis["fields"].get(key) for key in HYPOTHESIS_FIELDS
                        )
                        else "missing",
                        "All discovery fields must contain non-empty values.",
                    ),
                    requirement(
                        "HUMAN_APPROVAL",
                        "satisfied"
                        if hypothesis and hypothesis.get("approval")
                        else "missing",
                        "A human approver and rationale are required.",
                    ),
                ]
            )
        elif current_stage == "PROTOTYPING" and target_stage == "PLAYTEST_REQUIRED":
            for evidence_type, label in (
                ("build", "BUILD_PASS"),
                ("test", "TEST_PASS"),
                ("capture", "CAPTURE_PRESENT"),
            ):
                record = self._latest_evidence(state, evidence_type)
                if record is None:
                    status = "missing"
                    message = f"Current-source {evidence_type} evidence is required."
                    ids: list[str] = []
                elif not self._evidence_eligible_for_claim(record):
                    status = "invalid"
                    message = (
                        f"The latest {evidence_type} evidence artifact or "
                        "provenance is invalid; regenerate it."
                    )
                    ids = [record["evidence_id"]]
                elif record.get("result") != "passed" and evidence_type != "capture":
                    status = "failed"
                    message = f"The latest {evidence_type} evidence did not pass."
                    ids = [record["evidence_id"]]
                else:
                    status = "satisfied"
                    message = f"Current-source {evidence_type} evidence is present."
                    ids = [record["evidence_id"]]
                requirements.append(requirement(label, status, message, ids))
            requirements.append(
                requirement(
                    "HUMAN_APPROVAL",
                    "satisfied" if human_confirmed else "missing",
                    "A human must confirm this exact build is ready for "
                    "external playtest.",
                )
            )
        elif current_stage == "PROTOTYPING" and target_stage == "PROTOTYPE_DECISION":
            early_evidence = self._latest_evidence(state, "technical")
            if early_evidence and not self._evidence_eligible_for_claim(early_evidence):
                early_evidence = None
            if early_evidence is None:
                for evidence_type in ("build", "test"):
                    candidate = self._latest_evidence(state, evidence_type)
                    if (
                        candidate
                        and self._evidence_eligible_for_claim(candidate)
                        and candidate.get("result") == "failed"
                    ):
                        early_evidence = candidate
                        break
            requirements.extend(
                [
                    requirement(
                        "EARLY_DECISION_REASON",
                        "satisfied"
                        if reason in {"technical", "scope", "abandon"}
                        else "missing",
                        "An early decision reason must be technical, scope, or "
                        "abandon.",
                    ),
                    requirement(
                        "EARLY_DECISION_EVIDENCE",
                        "satisfied" if early_evidence else "missing",
                        "Technical, scope, abandonment, or failed run evidence "
                        "is required.",
                        [early_evidence["evidence_id"]] if early_evidence else [],
                    ),
                    requirement(
                        "HUMAN_APPROVAL",
                        "satisfied" if human_confirmed else "missing",
                        "A human approver and rationale are required for an "
                        "early decision.",
                    ),
                ]
            )
        elif (
            current_stage == "PLAYTEST_REQUIRED"
            and target_stage == "PROTOTYPE_DECISION"
        ):
            record = self._latest_evidence(state, "playtest")
            requirements.append(
                requirement(
                    "PLAYTEST_REPORT",
                    "missing"
                    if record is None
                    else "satisfied"
                    if self._evidence_eligible_for_claim(record)
                    else "invalid",
                    "A valid external playtest report scoped to the active "
                    "hypothesis and recorded protocol is required.",
                    [record["evidence_id"]] if record else [],
                )
            )
            requirements.append(
                requirement(
                    "HUMAN_APPROVAL",
                    "satisfied" if human_confirmed else "missing",
                    "A human must confirm the imported observations are "
                    "ready for a decision.",
                )
            )
        elif current_stage == "PROTOTYPE_DECISION":
            requirements.append(
                requirement(
                    "DECISION_COMMAND_REQUIRED",
                    "invalid",
                    "Use `loopforge decide keep|kill|refactor` for this transition.",
                )
            )
        result = (
            "pass"
            if all(item["status"] == "satisfied" for item in requirements)
            else "blocked"
        )
        diagnostics = [
            {
                "code": item["code"],
                "severity": "error",
                "message": item["message"],
                "details": {
                    "status": item["status"],
                    "evidence_ids": item["evidence_ids"],
                },
            }
            for item in requirements
            if item["status"] != "satisfied"
        ]
        return {
            "gate": target_stage,
            "from_stage": current_stage,
            "result": result,
            "requirements": requirements,
            "diagnostics": diagnostics,
            "observed_revision": state["revision"],
        }

    def advance(
        self,
        target_stage: str,
        expected_revision: int | None,
        reason: str | None = None,
        approver_id: str | None = None,
        approver_name: str | None = None,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        gate = self.gate_check(
            target_stage,
            reason,
            approver_id,
            approver_name,
            rationale,
        )
        if gate["result"] != "pass":
            raise GateBlockedError(
                f"Gate to {target_stage.upper()} is not satisfied.",
                {"gate": gate},
            )
        event, state = self.store.commit(
            "stage.transitioned",
            {
                "from": gate["from_stage"],
                "to": target_stage.upper(),
                "gate": target_stage.upper(),
                "requirements": gate["requirements"],
                "reason": reason,
                "approval": {
                    "approver_id": approver_id,
                    "approver_display_name": approver_name,
                    "identity_source": "local-declaration",
                    "rationale": rationale,
                    "approved_at": utc_now(),
                }
                if approver_id
                else None,
            },
            gate["observed_revision"]
            if expected_revision is None
            else expected_revision,
        )
        return {
            "from_stage": gate["from_stage"],
            "to_stage": target_stage.upper(),
            "committed_revision": event["revision"],
            "state": state,
        }

    def _active_hypothesis(self, state: dict[str, Any]) -> dict[str, Any] | None:
        hypothesis_id = state["active_experiment"].get("hypothesis_id")
        if not hypothesis_id:
            return None
        for event in reversed(self.store.read_events()):
            record = hypothesis_from_event(event)
            if record is None:
                continue
            if record.get("hypothesis_id") == hypothesis_id:
                return record
        return None

    def _latest_protocol(self, state: dict[str, Any]) -> dict[str, Any] | None:
        for event in reversed(self.store.read_events()):
            if event["event_type"] != "playtest.protocol.created":
                continue
            protocol = event["payload"]["protocol"]
            if (
                protocol.get("experiment_id")
                == state["active_experiment"]["experiment_id"]
                and protocol.get("hypothesis_revision")
                == state["active_experiment"]["hypothesis_revision"]
            ):
                result = dict(protocol)
                result["registration_revision"] = event["revision"]
                return result
        return None

    def _prototype_decision_entry(self) -> dict[str, Any] | None:
        for event in reversed(self.store.read_events()):
            if event["event_type"] != "stage.transitioned":
                continue
            payload = event["payload"]
            if payload.get("to") == "PROTOTYPE_DECISION":
                return payload
        return None

    def _latest_decision(
        self,
        experiment_id: str,
        hypothesis_revision: int | None,
    ) -> dict[str, Any] | None:
        for event in reversed(self.store.read_events()):
            if event["event_type"] != "decision.recorded":
                continue
            decision = event["payload"]["decision"]
            if (
                decision.get("experiment_id") == experiment_id
                and decision.get("hypothesis_revision") == hypothesis_revision
            ):
                result = dict(decision)
                result["event_id"] = event["event_id"]
                result["registration_revision"] = event["revision"]
                return result
        return None

    def _evidence_by_id(self) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for event in self.store.read_events():
            if event["event_type"] == "evidence.registered":
                record = dict(event["payload"]["evidence"])
                record["registration_revision"] = event["revision"]
                records[record["evidence_id"]] = record
            elif event["event_type"] == "evidence.revoked":
                record = records.get(event["payload"].get("evidence_id"))
                if record is not None:
                    record["revoked"] = True
                    record["revoked_at"] = event["payload"].get("revoked_at")
                    record["revocation_reason"] = event["payload"].get("reason")
                    record["revocation_event_id"] = event["event_id"]
        return records

    def _registered_artifact_paths(self) -> set[Path]:
        paths: set[Path] = set()
        for record in self._evidence_by_id().values():
            artifact = record.get("artifact", {})
            if artifact.get("kind") == "project-relative" and isinstance(
                artifact.get("path"), str
            ):
                paths.add((self.root / artifact["path"]).resolve())
        return paths

    def _latest_evidence(
        self, state: dict[str, Any], evidence_type: str
    ) -> dict[str, Any] | None:
        hypothesis_revision = state["active_experiment"].get("hypothesis_revision")
        source_identity = self._source_identity(self._registered_artifact_paths())
        evidence_records = self._evidence_by_id()
        for event in reversed(self.store.read_events()):
            if event["event_type"] != "evidence.registered":
                continue
            record = event["payload"]["evidence"]
            current_record = evidence_records.get(record.get("evidence_id"), {})
            if current_record.get("revoked"):
                continue
            subject = record.get("subject", {})
            if (
                record.get("type") == evidence_type
                and subject.get("experiment_id")
                == state["active_experiment"]["experiment_id"]
                and subject.get("hypothesis_revision") == hypothesis_revision
                and record.get("source_identity") == source_identity
            ):
                current = dict(record)
                current["registration_revision"] = event["revision"]
                return current
        return None

    def _evidence_eligible_for_claim(self, record: dict[str, Any]) -> bool:
        artifact = record.get("artifact", {})
        path = artifact_path(self.root, artifact)
        if (
            path is None
            or not path.is_file()
            or not checksum_matches(path, artifact.get("checksum"))
        ):
            return False
        evidence_type = record.get("type")
        if evidence_type == "capture":
            return valid_capture_image(path)
        if evidence_type in {"build", "test"} and (
            self.root / "project.godot"
        ).is_file():
            return (
                record.get("trust_level") == "tool_generated"
                and record.get("producer") == "loopforge.adapter.godot"
                and isinstance(record.get("run_id"), str)
            )
        if evidence_type == "playtest":
            return self._validated_playtest_evidence(record)
        return True

    def _validated_playtest_evidence(self, record: dict[str, Any]) -> bool:
        if (
            record.get("trust_level") != "human_attested"
            or record.get("producer") != "local-playtest-import"
        ):
            return False
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            return False
        protocol_id = metadata.get("protocol_id")
        report_id = metadata.get("report_id")
        if not isinstance(protocol_id, str) or not isinstance(report_id, str):
            return False
        artifact = record.get("artifact", {})
        expected_path = f".loopforge/playtests/{report_id}.json"
        if (
            artifact.get("kind") != "project-relative"
            or artifact.get("path") != expected_path
        ):
            return False
        path = artifact_path(self.root, artifact)
        if (
            path is None
            or not path.is_file()
            or not checksum_matches(path, artifact.get("checksum"))
        ):
            return False
        protocol = None
        for event in self.store.read_events():
            if event["event_type"] != "playtest.protocol.created":
                continue
            candidate = event["payload"]["protocol"]
            if candidate.get("protocol_id") == protocol_id:
                protocol = candidate
                break
        if protocol is None or not artifact_checksum_matches(
            self.root, protocol.get("path"), protocol.get("checksum")
        ):
            return False
        subject = record.get("subject", {})
        if (
            protocol.get("experiment_id") != subject.get("experiment_id")
            or protocol.get("hypothesis_revision") != subject.get("hypothesis_revision")
            or protocol.get("source_identity") != record.get("source_identity")
        ):
            return False
        try:
            report = normalize_playtest_report(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError, json.JSONDecodeError, InvalidStateError):
            return False
        return report["build_identity"] == protocol.get("build_identity")

    def _source_identity(
        self, excluded_paths: set[Path] | None = None
    ) -> dict[str, Any]:
        excluded_paths = {path.resolve() for path in (excluded_paths or set())}
        git = shutil.which("git")
        if git and (self.root / ".git").exists():
            commit = self._run_git(git, ["rev-parse", "HEAD"], allow_failure=True)
            status = self._run_git_bytes(
                git,
                ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            )
            dirty_digest = self._dirty_digest(status, excluded_paths)
            dirty = dirty_digest is not None
            identity: dict[str, Any] = {
                "kind": "git",
                "commit": commit.strip() if commit else None,
                "dirty": dirty,
            }
            if dirty:
                identity["dirty_digest"] = dirty_digest
            return identity
        return {
            "kind": "project-fingerprint",
            "digest": self._project_fingerprint(excluded_paths),
        }

    def _dirty_digest(self, status: bytes, excluded_paths: set[Path]) -> str | None:
        digest = hashlib.sha256()
        relevant = False
        tokens = status.split(b"\0")
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if not token:
                continue
            decoded = token.decode("utf-8", errors="surrogateescape")
            if len(decoded) < 4:
                continue
            change = decoded[:2]
            relative = decoded[3:]
            if "R" in change or "C" in change:
                index += 1
            if self._is_generated_path(relative):
                continue
            path = self.root / relative
            if path.resolve() in excluded_paths:
                continue
            relevant = True
            digest.update(change.encode("ascii", errors="replace"))
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            if path.is_symlink():
                digest.update(
                    os.readlink(path).encode("utf-8", errors="surrogateescape")
                )
            elif path.is_file():
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
        return f"sha256:{digest.hexdigest()}" if relevant else None

    def _project_fingerprint(self, excluded_paths: set[Path] | None = None) -> str:
        excluded_paths = excluded_paths or set()
        digest = hashlib.sha256()
        for path in sorted(self.root.rglob("*")):
            if (
                not path.is_file()
                or path.resolve() in excluded_paths
                or self._is_generated_path(path.relative_to(self.root).as_posix())
            ):
                continue
            relative = path.relative_to(self.root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(sha256_file(path).encode("ascii"))
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _is_generated_path(relative: str) -> bool:
        first = relative.replace("\\", "/").split("/", 1)[0]
        return first in GENERATED_DIRS

    def _run_git(
        self,
        executable: str,
        arguments: list[str],
        allow_failure: bool = False,
    ) -> str | None:
        result = subprocess.run(
            [executable, *arguments],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            if allow_failure:
                return None
            raise InvalidStateError(
                "Git could not produce a source identity.",
                "SOURCE_IDENTITY_UNAVAILABLE",
                {"stderr": result.stderr.strip()},
            )
        return result.stdout

    def _run_git_bytes(self, executable: str, arguments: list[str]) -> bytes:
        result = subprocess.run(
            [executable, *arguments],
            cwd=self.root,
            check=False,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise InvalidStateError(
                "Git could not inspect the working tree.",
                "SOURCE_IDENTITY_UNAVAILABLE",
                {"stderr": result.stderr.decode("utf-8", errors="replace").strip()},
            )
        return result.stdout

    @staticmethod
    def _next_actions(stage: str, snapshot_status: str) -> list[str]:
        if snapshot_status != "current":
            return ["validate", "reconcile --dry-run"]
        return {
            "DISCOVERY": ["hypothesis create", "gate check PROTOTYPING"],
            "PROTOTYPING": [
                "run build",
                "run test",
                "capture screenshot",
                "gate check PLAYTEST_REQUIRED",
            ],
            "PLAYTEST_REQUIRED": ["evidence add", "validate"],
            "PROTOTYPE_DECISION": ["evidence list", "validate"],
            "KILLED": ["history", "validate"],
        }.get(stage, ["status", "validate"])


def requirement(
    code: str,
    status: str,
    message: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "message": message,
        "evidence_ids": evidence_ids or [],
    }


def doctor_check(
    code: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "message": message,
        "details": details or {},
        "severity": "error" if status == "failed" else status,
    }


def doctor_diagnostic(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def godot_major_version(version: str | None) -> int | None:
    if not version:
        return None
    match = re.search(r"(?:^|\D)(\d+)(?:\.|$)", version)
    return int(match.group(1)) if match else None


def godot_error_lines(stdout: str, stderr: str) -> list[str]:
    """A Godot script or resource error can leave the process exit code at zero."""
    errors: list[str] = []
    for line in (stderr + "\n" + stdout).splitlines():
        stripped = line.strip()
        if re.match(r"^(?:SCRIPT ERROR|ERROR|FATAL ERROR):", stripped):
            errors.append(stripped)
    return errors[:20]


def valid_capture_image(path: Path) -> bool:
    """Reject mislabeled text while keeping manual image provenance explicit."""
    try:
        with path.open("rb") as handle:
            header = handle.read(32)
            if (
                header.startswith(b"\x89PNG\r\n\x1a\n")
                and header[12:16] == b"IHDR"
                and int.from_bytes(header[8:12], "big") == 13
            ):
                return (
                    int.from_bytes(header[16:20], "big") > 0
                    and int.from_bytes(header[20:24], "big") > 0
                )
            if header.startswith(b"\xff\xd8\xff"):
                handle.seek(-2, os.SEEK_END)
                return handle.read(2) == b"\xff\xd9"
            if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
                return int.from_bytes(header[4:8], "little") + 8 <= path.stat().st_size
    except (OSError, ValueError):
        return False
    return False


def hypothesis_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event_type") not in {"hypothesis.created", "decision.recorded"}:
        return None
    record = event.get("payload", {}).get("hypothesis")
    return record if isinstance(record, dict) else None


def latest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return max(records, key=lambda record: record.get("registration_revision", -1))


def claim(
    status: str,
    evidence_records: list[dict[str, Any]],
    decision_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    decisions = decision_records or []
    return {
        "status": status,
        "evidence_ids": [
            record["evidence_id"]
            for record in evidence_records
            if isinstance(record.get("evidence_id"), str)
        ],
        "decision_event_ids": [
            record["event_id"]
            for record in decisions
            if isinstance(record.get("event_id"), str)
        ],
    }


def artifact_path(root: Path, artifact: Any) -> Path | None:
    if not isinstance(artifact, dict):
        return None
    kind = artifact.get("kind")
    raw_path = artifact.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    try:
        candidate = Path(raw_path)
        if kind == "project-relative":
            if candidate.is_absolute():
                return None
            resolved = (root / candidate).resolve()
            if not resolved.is_relative_to(root.resolve()):
                return None
            return resolved
        if kind == "absolute" and candidate.is_absolute():
            return candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return None


def artifact_checksum_matches(root: Path, path: Any, checksum: Any) -> bool:
    candidate = artifact_path(root, {"kind": "project-relative", "path": path})
    return (
        candidate is not None
        and candidate.is_file()
        and checksum_matches(candidate, checksum)
    )


def checksum_matches(path: Path, checksum: Any) -> bool:
    if not isinstance(checksum, str):
        return False
    try:
        return checksum == sha256_file(path)
    except OSError:
        return False


def diagnostic(
    code: str,
    message: str,
    event_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostic_details = {"event_id": event_id}
    if details:
        diagnostic_details.update(details)
    return {
        "code": code,
        "severity": "error",
        "message": message,
        "details": diagnostic_details,
    }


def parse_hypothesis(content: str, suffix: str) -> dict[str, str]:
    if suffix == ".json":
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidStateError(
                "The hypothesis JSON is invalid.",
                "HYPOTHESIS_SCHEMA_INVALID",
                {"cause": str(exc)},
            ) from exc
        if not isinstance(parsed, dict):
            raise InvalidStateError(
                "The hypothesis JSON must be an object.", "HYPOTHESIS_SCHEMA_INVALID"
            )
        fields = {key: str(parsed.get(key, "")).strip() for key in HYPOTHESIS_FIELDS}
    else:
        fields: dict[str, str] = {}
        current: str | None = None
        sections: dict[str, list[str]] = {}
        for line in content.splitlines():
            if line.startswith("##"):
                heading = line.lstrip("#").strip()
                normalized = re.sub(r"[^a-z0-9]", "", heading.lower())
                current = HYPOTHESIS_HEADINGS.get(normalized)
                if current:
                    sections.setdefault(current, [])
                continue
            if current:
                sections[current].append(line)
        fields = {key: "\n".join(value).strip() for key, value in sections.items()}
        fields = {key: fields.get(key, "") for key in HYPOTHESIS_FIELDS}

    missing = [key for key, value in fields.items() if not value]
    if missing:
        raise InvalidStateError(
            "The hypothesis is missing required fields.",
            "HYPOTHESIS_SCHEMA_INVALID",
            {"missing": missing},
        )
    return fields


def _decode_process_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def playtest_build_identity(source_identity: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(source_identity))


def normalize_playtest_report(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise InvalidStateError(
            "The playtest report must be a JSON object.",
            "PLAYTEST_REPORT_INVALID",
        )
    missing = [field for field in PLAYTEST_REPORT_FIELDS if field not in report]
    if missing:
        raise InvalidStateError(
            "The playtest report is missing required fields.",
            "PLAYTEST_REPORT_INVALID",
            {"missing": missing},
        )
    unknown = sorted(set(report) - set(PLAYTEST_REPORT_FIELDS))
    if unknown:
        raise InvalidStateError(
            f"The playtest report contains unknown fields: {', '.join(unknown)}.",
            "PLAYTEST_REPORT_INVALID",
            {"unknown": unknown},
        )
    if report["consent_status"] not in PLAYTEST_CONSENT_VALUES:
        raise InvalidStateError(
            "Playtest consent must be obtained or explicitly not required.",
            "PLAYTEST_CONSENT_INVALID",
        )
    cleaned: dict[str, Any] = {"consent_status": report["consent_status"]}
    for field in PLAYTEST_LIST_FIELDS:
        value = report[field]
        if not isinstance(value, list) or (field == "raw_observations" and not value):
            raise InvalidStateError(
                f"Playtest {field} must be a "
                f"{'non-empty ' if field == 'raw_observations' else ''}list.",
                "PLAYTEST_REPORT_INVALID",
                {"field": field},
            )
        if len(value) > MAX_PLAYTEST_ITEMS:
            raise InvalidStateError(
                f"Playtest {field} has too many entries.",
                "PLAYTEST_REPORT_INVALID",
                {"field": field, "max_items": MAX_PLAYTEST_ITEMS},
            )
        items: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise InvalidStateError(
                    f"Every playtest {field} entry must be non-empty text.",
                    "PLAYTEST_REPORT_INVALID",
                    {"field": field, "index": index},
                )
            cleaned_item = item.strip()
            if len(cleaned_item) > MAX_PLAYTEST_FIELD_CHARS:
                raise InvalidStateError(
                    f"A playtest {field} entry is too long.",
                    "PLAYTEST_REPORT_INVALID",
                    {
                        "field": field,
                        "index": index,
                        "max_characters": MAX_PLAYTEST_FIELD_CHARS,
                    },
                )
            items.append(cleaned_item)
        cleaned[field] = items
    for field in PLAYTEST_TEXT_FIELDS:
        value = report[field]
        if not isinstance(value, str) or not value.strip():
            raise InvalidStateError(
                f"Playtest {field} must be non-empty text.",
                "PLAYTEST_REPORT_INVALID",
                {"field": field},
            )
        cleaned_value = value.strip()
        if len(cleaned_value) > MAX_PLAYTEST_FIELD_CHARS:
            raise InvalidStateError(
                f"Playtest {field} is too long.",
                "PLAYTEST_REPORT_INVALID",
                {"field": field, "max_characters": MAX_PLAYTEST_FIELD_CHARS},
            )
        cleaned[field] = cleaned_value
    return {field: cleaned[field] for field in PLAYTEST_REPORT_FIELDS}


def validate_playtest_report(report: Any) -> None:
    normalize_playtest_report(report)
