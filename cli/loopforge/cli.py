from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .agent import AgentSupervisor
from .errors import InvalidStateError, LoopforgeError
from .installation import install_skills, uninstall_skills
from .project import EVIDENCE_TYPES, MANUAL_TRUST_LEVELS, LoopforgeProject
from .storage import utc_now
from .version import __version__


def build_global_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", default=".")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--version", action="store_true")
    return parser


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loopforge",
        description="Deterministic project state and evidence CLI.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize project-local Loopforge state.")
    commands.add_parser("inspect", help="Inspect the project and available tools.")
    commands.add_parser("doctor", help="Diagnose state and engine compatibility.")
    commands.add_parser("status", help="Show current state and next actions.")
    commands.add_parser("validate", help="Validate project state and event history.")
    commands.add_parser("history", help="Show committed project events.")

    agent = commands.add_parser("agent", help="Manage the project-local Kura daemon.")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    agent_start = agent_commands.add_parser(
        "start", help="Start and synchronize the local agent daemon."
    )
    agent_start.add_argument("--port", type=int)
    agent_start.add_argument("--dope-binary")
    agent_stop = agent_commands.add_parser(
        "stop", help="Stop the project-local agent daemon."
    )
    agent_stop.add_argument("--dope-binary")
    agent_commands.add_parser("status", help="Show daemon health and version.")
    agent_doctor = agent_commands.add_parser(
        "doctor", help="Diagnose the local agent integration."
    )
    agent_doctor.add_argument("--dope-binary")
    agent_commands.add_parser("context", help="Show the redacted game-project context.")
    agent_commands.add_parser(
        "sync", help="Synchronize game-project context to the daemon."
    )

    setup = commands.add_parser(
        "setup", help="Install bundled Loopforge Skills for an agent host."
    )
    setup.add_argument(
        "--host",
        choices=("codex",),
        default="codex",
        help="Agent host to configure (default: codex).",
    )
    setup.add_argument(
        "--skills-root",
        type=Path,
        help="Override the host Skills directory.",
    )
    setup.add_argument(
        "--force",
        action="store_true",
        help="Replace conflicts after preserving timestamped backups.",
    )
    setup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the plan without changing files.",
    )
    setup.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove managed Loopforge Skills instead of installing them.",
    )

    hypothesis = commands.add_parser("hypothesis", help="Create or show a hypothesis.")
    hypothesis_commands = hypothesis.add_subparsers(
        dest="hypothesis_command", required=True
    )
    hypothesis_create = hypothesis_commands.add_parser(
        "create", help="Register a hypothesis file."
    )
    hypothesis_create.add_argument("--file", required=True, type=Path)
    hypothesis_create.add_argument("--approver-id")
    hypothesis_create.add_argument("--approver-name")
    hypothesis_create.add_argument("--rationale")
    hypothesis_commands.add_parser("show", help="Show the active hypothesis.")

    gate = commands.add_parser("gate", help="Check a stage transition gate.")
    gate_commands = gate.add_subparsers(dest="gate_command", required=True)
    gate_check = gate_commands.add_parser("check", help="Check a target stage gate.")
    gate_check.add_argument("stage")
    gate_check.add_argument("--reason", choices=("technical", "scope", "abandon"))
    gate_check.add_argument("--approver-id")
    gate_check.add_argument("--approver-name")
    gate_check.add_argument("--rationale")

    advance = commands.add_parser("advance", help="Advance through a passing gate.")
    advance.add_argument("stage")
    advance.add_argument("--reason", choices=("technical", "scope", "abandon"))
    advance.add_argument("--approver-id")
    advance.add_argument("--approver-name")
    advance.add_argument("--rationale")

    run = commands.add_parser(
        "run", help="Run an engine operation and record evidence."
    )
    run.add_argument("operation", choices=("build", "test"))
    run.add_argument("--timeout", type=float, default=120.0)

    capture = commands.add_parser("capture", help="Register a runtime capture.")
    capture_commands = capture.add_subparsers(dest="capture_command", required=True)
    screenshot = capture_commands.add_parser("screenshot")
    screenshot.add_argument("--file", required=True, type=Path)

    playtest = commands.add_parser(
        "playtest", help="Create or import playtest artifacts."
    )
    playtest_commands = playtest.add_subparsers(dest="playtest_command", required=True)
    playtest_create = playtest_commands.add_parser("create")
    playtest_create.add_argument("--protocol", required=True, type=Path)
    playtest_import = playtest_commands.add_parser("import")
    playtest_import.add_argument("--file", required=True, type=Path)

    decide = commands.add_parser("decide", help="Record a prototype decision.")
    decide.add_argument("decision", choices=("keep", "kill", "refactor"))
    decide.add_argument("--evidence", action="append", required=True)
    decide.add_argument("--approver-id", required=True)
    decide.add_argument("--approver-name", required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument("--file", type=Path)

    reconcile = commands.add_parser("reconcile", help="Plan or apply state recovery.")
    reconcile_mode = reconcile.add_mutually_exclusive_group(required=True)
    reconcile_mode.add_argument("--dry-run", action="store_true")
    reconcile_mode.add_argument("--yes", action="store_true", help="Apply the plan.")

    evidence = commands.add_parser("evidence", help="Register or list evidence.")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_add = evidence_commands.add_parser(
        "add", help="Register a local artifact."
    )
    evidence_add.add_argument("--type", required=True, choices=EVIDENCE_TYPES)
    evidence_add.add_argument("--file", required=True, type=Path)
    evidence_add.add_argument(
        "--trust",
        choices=MANUAL_TRUST_LEVELS,
        default="manually_imported",
    )
    evidence_add.add_argument(
        "--result",
        choices=("passed", "failed", "observation"),
        default="observation",
    )
    evidence_add.add_argument("--producer")
    evidence_commands.add_parser("list", help="List registered evidence.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    global_parser = build_global_parser()
    global_options, remaining = global_parser.parse_known_args(arguments)
    if global_options.version:
        print(__version__)
        return 0

    parser = build_command_parser()
    try:
        command = parser.parse_args(remaining)
    except SystemExit as exc:
        return int(exc.code)

    project = LoopforgeProject(Path(global_options.project))
    command_name = canonical_command_name(command)
    observed_revision: int | None = None
    try:
        data = execute(project, command, global_options.expected_revision)
        observed_revision = data.get("observed_revision")
        if observed_revision is None:
            observed_revision = data.get("committed_revision")
        if observed_revision is None and isinstance(data.get("state"), dict):
            observed_revision = data["state"].get("revision")

        ok = not (
            (command_name == "validate" and not data["valid"])
            or (command_name == "gate.check" and data.get("result") != "pass")
            or (command_name == "doctor" and not data["healthy"])
        )
        diagnostics = data.pop("diagnostics", [])
        envelope = make_envelope(
            command_name,
            ok=ok,
            data=data,
            diagnostics=diagnostics,
            observed_revision=observed_revision,
        )
        emit(envelope, global_options.format, global_options.quiet)
        if ok:
            return 0
        return 3 if command_name == "gate.check" else 2
    except LoopforgeError as exc:
        diagnostic = {
            "code": exc.diagnostic_code,
            "severity": "error",
            "message": exc.message,
            "details": exc.details,
        }
        envelope = make_envelope(
            command_name,
            ok=False,
            data={},
            diagnostics=[diagnostic],
            observed_revision=observed_revision,
        )
        emit(envelope, global_options.format, global_options.quiet)
        return exc.exit_code
    except KeyboardInterrupt:
        diagnostic = {
            "code": "COMMAND_INTERRUPTED",
            "severity": "error",
            "message": "The command was interrupted.",
            "details": {},
        }
        emit(
            make_envelope(command_name, False, {}, [diagnostic], observed_revision),
            global_options.format,
            global_options.quiet,
        )
        return 1


def execute(
    project: LoopforgeProject,
    command: argparse.Namespace,
    expected_revision: int | None,
) -> dict[str, Any]:
    if command.command == "init":
        return project.init()
    if command.command == "inspect":
        return project.inspect()
    if command.command == "doctor":
        return project.doctor()
    if command.command == "status":
        return project.status()
    if command.command == "validate":
        return project.validate()
    if command.command == "history":
        return project.history()
    if command.command == "agent":
        supervisor = AgentSupervisor(
            project,
            getattr(command, "dope_binary", None),
        )
        if command.agent_command == "start":
            status = supervisor.start(command.port)
            synchronized = supervisor.sync_context()
            return {"status": status, **synchronized}
        if command.agent_command == "stop":
            return supervisor.stop()
        if command.agent_command == "status":
            return supervisor.status()
        if command.agent_command == "doctor":
            return supervisor.doctor()
        if command.agent_command == "context":
            return supervisor.context()
        if command.agent_command == "sync":
            return supervisor.sync_context()
    if command.command == "setup":
        if command.uninstall:
            return uninstall_skills(
                host=command.host,
                explicit_root=command.skills_root,
                force=command.force,
                dry_run=command.dry_run,
            )
        return install_skills(
            host=command.host,
            explicit_root=command.skills_root,
            force=command.force,
            dry_run=command.dry_run,
        )
    if command.command == "hypothesis":
        if command.hypothesis_command == "create":
            return project.create_hypothesis(
                command.file,
                expected_revision,
                command.approver_id,
                command.approver_name,
                command.rationale,
            )
        if command.hypothesis_command == "show":
            return project.show_hypothesis()
    if command.command == "gate" and command.gate_command == "check":
        return project.gate_check(
            command.stage,
            command.reason,
            command.approver_id,
            command.approver_name,
            command.rationale,
        )
    if command.command == "advance":
        return project.advance(
            command.stage,
            expected_revision,
            command.reason,
            command.approver_id,
            command.approver_name,
            command.rationale,
        )
    if command.command == "run":
        return project.run_engine(command.operation, expected_revision, command.timeout)
    if command.command == "capture" and command.capture_command == "screenshot":
        return project.capture_screenshot(command.file, expected_revision)
    if command.command == "playtest":
        if command.playtest_command == "create":
            return project.create_playtest_protocol(command.protocol, expected_revision)
        if command.playtest_command == "import":
            return project.import_playtest(command.file, expected_revision)
    if command.command == "decide":
        return project.decide(
            command.decision,
            command.evidence,
            expected_revision,
            command.approver_id,
            command.approver_name,
            command.rationale,
            command.file,
        )
    if command.command == "reconcile":
        return project.reconcile(apply=command.yes)
    if command.command == "evidence":
        if command.evidence_command == "add":
            return project.add_evidence(
                command.type,
                command.file,
                command.trust,
                command.result,
                expected_revision,
                command.producer,
            )
        if command.evidence_command == "list":
            return project.list_evidence()
    raise InvalidStateError(
        "The requested command is not implemented.",
        "COMMAND_NOT_IMPLEMENTED",
    )


def canonical_command_name(command: argparse.Namespace) -> str:
    if command.command == "evidence":
        return f"evidence.{command.evidence_command}"
    if command.command == "hypothesis":
        return f"hypothesis.{command.hypothesis_command}"
    if command.command == "gate":
        return f"gate.{command.gate_command}"
    if command.command == "capture":
        return f"capture.{command.capture_command}"
    if command.command == "playtest":
        return f"playtest.{command.playtest_command}"
    if command.command == "agent":
        return f"agent.{command.agent_command}"
    return command.command


def make_envelope(
    command: str,
    ok: bool,
    data: dict[str, Any],
    diagnostics: list[dict[str, Any]],
    observed_revision: int | None,
) -> dict[str, Any]:
    output_data = dict(data)
    committed_revision = output_data.pop("committed_revision", None)
    envelope: dict[str, Any] = {
        "schema_version": 1,
        "tool_version": __version__,
        "command": command,
        "ok": ok,
        "generated_at": utc_now(),
        "data": output_data,
        "diagnostics": sorted(
            diagnostics,
            key=lambda item: (
                severity_order(item.get("severity")),
                str(item.get("code", "")),
                json.dumps(item.get("details", {}), sort_keys=True),
            ),
        ),
    }
    if observed_revision is not None:
        envelope["observed_revision"] = observed_revision
    if committed_revision is not None:
        envelope["committed_revision"] = committed_revision
    return envelope


def severity_order(severity: Any) -> int:
    return {"error": 0, "warning": 1, "info": 2}.get(str(severity), 3)


def emit(envelope: dict[str, Any], output_format: str, quiet: bool) -> None:
    if output_format == "json":
        print(json.dumps(envelope, ensure_ascii=True, sort_keys=True))
        return
    if quiet and envelope["ok"]:
        return
    stream = sys.stdout if envelope["ok"] else sys.stderr
    if envelope["ok"]:
        print_human_success(envelope, stream)
    else:
        print_human_failure(envelope, stream)


def print_human_success(envelope: dict[str, Any], stream: Any) -> None:
    command = envelope["command"]
    data = envelope["data"]
    if command == "setup":
        prefix = "Plan" if data["dry_run"] else "Loopforge Skills"
        if "removed" in data:
            summary = f"removed {data['removed']}, unchanged {data['skipped']}"
        else:
            summary = (
                f"installed {data['installed']}, updated {data['updated']}, "
                f"unchanged {data['skipped']}"
            )
        print(f"{prefix}: {summary}", file=stream)
        print(f"Location: {data['skills_root']}", file=stream)
        for skill in data["skills"]:
            if "backup" in skill:
                print(f"Backup: {skill['name']} -> {skill['backup']}", file=stream)
        return
    if command == "status":
        print(f"Stage: {data['stage']}", file=stream)
        print(f"Revision: {data['observed_revision']}", file=stream)
        print(f"Snapshot: {data['snapshot_status']}", file=stream)
        actions = ", ".join(data["next_allowed_actions"])
        print(f"Next actions: {actions}", file=stream)
        return
    if command == "history":
        for event in data["events"]:
            print(
                f"{event['revision']:>4} {event['event_type']} {event['event_id']}",
                file=stream,
            )
        return
    if command == "evidence.list":
        for record in data["evidence"]:
            print(
                f"{record['evidence_id']} {record['type']} "
                f"{record['artifact']['checksum']}",
                file=stream,
            )
        return
    print(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), file=stream)


def print_human_failure(envelope: dict[str, Any], stream: Any) -> None:
    for diagnostic in envelope["diagnostics"]:
        print(
            f"{diagnostic['severity'].upper()} {diagnostic['code']}: "
            f"{diagnostic['message']}",
            file=stream,
        )


if __name__ == "__main__":
    raise SystemExit(main())
