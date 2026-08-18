#!/usr/bin/env python3
"""Materialize prototype-gameplay draft artifacts without silent overwrites."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ARTIFACTS = {
    "hypothesis": "hypothesis.md",
    "prototype-brief": "prototype-brief.md",
    "playtest-protocol": "playtest-protocol.md",
    "playtest-report": "playtest-report.json",
    "decision-review": "decision-review.md",
}


class WorkspaceError(Exception):
    def __init__(
        self, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create production-ready Loopforge prototype draft files.",
    )
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--artifact", required=True, choices=(*ARTIFACTS, "all"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args()


def sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def ensure_within_project(project: Path, path: Path) -> None:
    try:
        path.relative_to(project)
    except ValueError as exc:
        raise WorkspaceError(
            "OUTPUT_OUTSIDE_PROJECT",
            "Draft output must remain inside the project root.",
            {"project": str(project), "output": str(path)},
        ) from exc


def resolve_destinations(
    project: Path,
    artifact: str,
    output: Path | None,
) -> list[tuple[str, Path, Path]]:
    if artifact == "all" and output is not None:
        raise WorkspaceError(
            "OUTPUT_AMBIGUOUS",
            "--output can only be used with one artifact.",
        )
    names = list(ARTIFACTS) if artifact == "all" else [artifact]
    assets = Path(__file__).resolve().parent.parent / "assets"
    destinations: list[tuple[str, Path, Path]] = []
    for name in names:
        source = assets / ARTIFACTS[name]
        if not source.is_file():
            raise WorkspaceError(
                "TEMPLATE_MISSING",
                "A required skill template is unavailable.",
                {"artifact": name, "template": str(source)},
            )
        requested = (
            output if output is not None else Path(".loopforge/drafts") / source.name
        )
        destination = requested if requested.is_absolute() else project / requested
        destination = destination.resolve()
        ensure_within_project(project, destination)
        destinations.append((name, source, destination))
    return destinations


def preflight(
    destinations: list[tuple[str, Path, Path]],
    force: bool,
) -> list[tuple[str, Path, Path, bytes, str]]:
    prepared: list[tuple[str, Path, Path, bytes, str]] = []
    conflicts: list[str] = []
    for name, source, destination in destinations:
        content = source.read_bytes()
        action = "created"
        if destination.exists():
            if not destination.is_file():
                conflicts.append(str(destination))
                continue
            if destination.read_bytes() == content:
                action = "unchanged"
            elif force:
                action = "replaced"
            else:
                conflicts.append(str(destination))
                continue
        prepared.append((name, source, destination, content, action))
    if conflicts:
        raise WorkspaceError(
            "DRAFT_CONFLICT",
            "Existing draft files differ from the templates; rerun with --force to replace them.",
            {"paths": sorted(conflicts)},
        )
    return prepared


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def materialize(arguments: argparse.Namespace) -> dict[str, Any]:
    project = arguments.project.expanduser().resolve()
    if not project.is_dir():
        raise WorkspaceError(
            "PROJECT_MISSING",
            "The project root must be an existing directory.",
            {"project": str(project)},
        )
    state_dir = project / ".loopforge"
    required_state = (state_dir / "project.json", state_dir / "events.jsonl")
    missing_state = [str(path) for path in required_state if not path.is_file()]
    if missing_state:
        raise WorkspaceError(
            "PROJECT_NOT_INITIALIZED",
            "Initialize Loopforge before creating workflow drafts.",
            {"missing": missing_state, "remediation": "Run `loopforge init`."},
        )

    destinations = resolve_destinations(project, arguments.artifact, arguments.output)
    prepared = preflight(destinations, arguments.force)
    results = []
    for name, source, destination, content, action in prepared:
        if action != "unchanged":
            atomic_write(destination, content)
        results.append(
            {
                "artifact": name,
                "path": destination.relative_to(project).as_posix(),
                "action": action,
                "template": str(source),
                "checksum": sha256(content),
            }
        )
    return {"project": str(project), "artifacts": results}


def emit(payload: dict[str, Any], output_format: str, ok: bool) -> None:
    envelope = {"schema_version": 1, "ok": ok, **payload}
    if output_format == "json":
        print(json.dumps(envelope, sort_keys=True))
        return
    stream = sys.stdout if ok else sys.stderr
    if ok:
        for item in payload["artifacts"]:
            print(f"{item['action']}: {item['path']}", file=stream)
    else:
        diagnostic = payload["diagnostics"][0]
        print(f"ERROR {diagnostic['code']}: {diagnostic['message']}", file=stream)


def main() -> int:
    arguments = parse_args()
    try:
        result = materialize(arguments)
    except (OSError, UnicodeError) as exc:
        error = WorkspaceError(
            "WORKSPACE_IO_ERROR",
            "The draft workspace could not be prepared.",
            {"cause": str(exc)},
        )
    except WorkspaceError as exc:
        error = exc
    else:
        emit(result, arguments.format, ok=True)
        return 0

    emit(
        {
            "diagnostics": [
                {
                    "code": error.code,
                    "severity": "error",
                    "message": error.message,
                    "details": error.details,
                }
            ]
        },
        arguments.format,
        ok=False,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
