#!/usr/bin/env python3
"""Validate completed prototype-gameplay drafts before CLI registration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_HEADINGS = {
    "hypothesis": (
        "intended player",
        "platform",
        "player fantasy",
        "core verb",
        "moment to moment loop",
        "hypothesis",
        "constraints",
        "non-goals",
        "cheapest validation",
        "keep signals",
        "kill signals",
        "approval checkpoint",
    ),
    "prototype-brief": (
        "identity",
        "experimental question",
        "core loop",
        "controls",
        "success, failure, and restart",
        "scope",
        "non-goals",
        "shortcuts and disposable assumptions",
        "verification plan",
        "exit conditions",
    ),
    "playtest-protocol": (
        "build identity",
        "participant and consent",
        "neutral task",
        "observe",
        "stop conditions",
    ),
    "decision-review": (
        "identity",
        "hypothesis and declared signals",
        "evidence considered",
        "strongest supporting observations",
        "strongest contradicting observations",
        "confounds and limitations",
        "confidence",
        "recommendation",
        "human confirmation",
    ),
}
REPORT_FIELDS = (
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
LIST_FIELDS = (
    "raw_observations",
    "confusion_points",
    "failure_points",
    "abandonment_points",
    "strategies",
)
PLACEHOLDER = re.compile(r"<[^<>]+>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a completed prototype workflow draft."
    )
    parser.add_argument(
        "--artifact",
        required=True,
        choices=(*REQUIRED_HEADINGS, "playtest-report"),
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args()


def issue(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "message": message,
        "details": details or {},
    }


def has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return PLACEHOLDER.search(value) is not None
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


def markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in content.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def validate_markdown(artifact: str, content: str) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    sections = markdown_sections(content)
    missing = [
        heading for heading in REQUIRED_HEADINGS[artifact] if not sections.get(heading)
    ]
    if missing:
        diagnostics.append(
            issue(
                "DRAFT_SECTIONS_MISSING",
                "The draft is missing required non-empty sections.",
                {"sections": missing},
            )
        )
    placeholder_sections = [
        heading for heading, value in sections.items() if PLACEHOLDER.search(value)
    ]
    if placeholder_sections:
        diagnostics.append(
            issue(
                "DRAFT_PLACEHOLDERS_REMAIN",
                "Replace every template placeholder before registration.",
                {"sections": sorted(placeholder_sections)},
            )
        )
    return diagnostics


def validate_report(report: Any) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return [
            issue(
                "PLAYTEST_REPORT_INVALID", "The playtest report must be a JSON object."
            )
        ]
    diagnostics: list[dict[str, Any]] = []
    missing = [field for field in REPORT_FIELDS if field not in report]
    if missing:
        diagnostics.append(
            issue(
                "PLAYTEST_FIELDS_MISSING",
                "The playtest report is missing required fields.",
                {"fields": missing},
            )
        )
    if report.get("consent_status") not in {"obtained", "not_required"}:
        diagnostics.append(
            issue(
                "PLAYTEST_CONSENT_INVALID",
                "Consent must be obtained or legitimately not_required before import.",
            )
        )
    for field in LIST_FIELDS:
        value = report.get(field)
        if not isinstance(value, list) or (field == "raw_observations" and not value):
            diagnostics.append(
                issue(
                    "PLAYTEST_FIELD_INVALID",
                    f"{field} must be a {'non-empty ' if field == 'raw_observations' else ''}list.",
                    {"field": field},
                )
            )
    for field in (
        "build_identity",
        "participant_context",
        "assistance_given",
        "comprehension_time",
        "replay_behavior",
        "interpretation",
        "sensitive_data",
    ):
        value = report.get(field)
        if not isinstance(value, str) or not value.strip():
            diagnostics.append(
                issue(
                    "PLAYTEST_FIELD_INVALID",
                    f"{field} must be a non-empty string.",
                    {"field": field},
                )
            )
    if has_placeholder(report):
        diagnostics.append(
            issue(
                "DRAFT_PLACEHOLDERS_REMAIN",
                "Replace every template placeholder before import.",
            )
        )
    return diagnostics


def validate(arguments: argparse.Namespace) -> dict[str, Any]:
    path = arguments.file.expanduser().resolve()
    if not path.is_file():
        return {
            "path": str(path),
            "diagnostics": [
                issue("DRAFT_FILE_MISSING", "The draft file does not exist.")
            ],
        }
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {
            "path": str(path),
            "diagnostics": [
                issue(
                    "DRAFT_FILE_UNREADABLE",
                    "The draft cannot be read as UTF-8.",
                    {"cause": str(exc)},
                )
            ],
        }
    if arguments.artifact == "playtest-report":
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            diagnostics = [
                issue(
                    "PLAYTEST_REPORT_INVALID_JSON",
                    "The playtest report is not valid JSON.",
                    {"cause": str(exc)},
                )
            ]
        else:
            diagnostics = validate_report(parsed)
    else:
        diagnostics = validate_markdown(arguments.artifact, content)
    return {
        "path": str(path),
        "artifact": arguments.artifact,
        "diagnostics": diagnostics,
    }


def emit(result: dict[str, Any], output_format: str) -> None:
    ok = not result["diagnostics"]
    if output_format == "json":
        print(json.dumps({"schema_version": 1, "ok": ok, **result}, sort_keys=True))
        return
    stream = sys.stdout if ok else sys.stderr
    if ok:
        print(f"valid: {result['path']}", file=stream)
    else:
        for diagnostic in result["diagnostics"]:
            print(f"ERROR {diagnostic['code']}: {diagnostic['message']}", file=stream)


def main() -> int:
    arguments = parse_args()
    result = validate(arguments)
    emit(result, arguments.format)
    return 0 if not result["diagnostics"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
