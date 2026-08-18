#!/usr/bin/env python3
"""Validate a Loopforge game-design contract and its human-readable brief."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PLACEHOLDER = re.compile(r"<[^<>]+>|\bTODO\b")
CHECKSUM = re.compile(r"sha256:[0-9a-f]{64}\Z")
MARKDOWN_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
BUCKETS = {"mvp", "vertical_slice", "later", "cut"}
LOOPS = {"moment", "session", "meta"}
CONFIDENCE = {"low", "medium", "high"}
IMPACT = {"low", "medium", "high"}
ASSUMPTION_STATUS = {"planned", "validated", "invalidated", "unknown"}
GDD_REQUIRED_SECTIONS = (
    "Document Identity",
    "Executive Summary",
    "Source Inventory",
    "Design Nucleus",
    "Target Player and Product Context",
    "Player Promise",
    "Player Verbs, Controls, and Goals",
    "Moment Loop",
    "Session Loop",
    "Meta Loop",
    "Systems",
    "Progression and Economy",
    "Content and Experience Coverage",
    "UX, Onboarding, and Accessibility",
    "Narrative and World",
    "Art and Audio Direction",
    "Technical and Platform Constraints",
    "Scope Gate",
    "Vertical Slice",
    "Production Plan",
    "Assumption and Evidence Ledger",
    "Risk Register",
    "Validation and Investment Decision",
    "Non-Goals",
    "Approval",
    "Version History",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a game-design contract.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args()


def issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": "error", "message": message, "details": details}


def concrete(value: Any) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER.search(value)
    )


def concrete_or_unknown(value: Any) -> bool:
    return concrete(value) or value == "unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def relative_path(project: Path, value: Any) -> tuple[Path | None, str | None]:
    if not concrete(value):
        return None, "path must be concrete"
    candidate = Path(value)
    if candidate.is_absolute():
        return None, "path must be project-relative"
    resolved = (project / candidate).resolve()
    try:
        resolved.relative_to(project.resolve())
    except ValueError:
        return None, "path escapes project root"
    return resolved, None


def markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = MARKDOWN_HEADING.match(line)
        if heading:
            current = heading.group(1).strip().casefold()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def section_is_complete(lines: list[str]) -> bool:
    body = "\n".join(lines)
    if PLACEHOLDER.search(body):
        return False
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if re.fullmatch(r"\|?[\s:|-]+\|?", value):
            continue
        return True
    return False


def check_design_document(
    path: Path, checksum: Any, errors: list[dict[str, Any]]
) -> None:
    if not isinstance(checksum, str) or not CHECKSUM.fullmatch(checksum):
        errors.append(
            issue(
                "CHECKSUM_INVALID",
                "design_document.checksum must be a sha256 digest",
                path="design_document.checksum",
            )
        )
    if not path.is_file():
        errors.append(
            issue(
                "DOCUMENT_MISSING",
                "the complete game design document does not exist",
                path=str(path),
            )
        )
        return
    if (
        isinstance(checksum, str)
        and CHECKSUM.fullmatch(checksum)
        and checksum != sha256(path)
    ):
        errors.append(
            issue(
                "DOCUMENT_CHECKSUM",
                "design document checksum does not match",
                path=str(path),
            )
        )
    try:
        sections = markdown_sections(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        errors.append(issue("DOCUMENT_READ", str(exc), path=str(path)))
        return
    for section in GDD_REQUIRED_SECTIONS:
        body = sections.get(section.casefold())
        if body is None:
            errors.append(
                issue(
                    "DOCUMENT_SECTION_MISSING",
                    f"design document is missing section: {section}",
                    path=str(path),
                    section=section,
                )
            )
        elif not section_is_complete(body):
            errors.append(
                issue(
                    "DOCUMENT_SECTION_INCOMPLETE",
                    f"design document section is incomplete: {section}",
                    path=str(path),
                    section=section,
                )
            )


def require_text(
    obj: dict[str, Any], key: str, path: str, errors: list[dict[str, Any]]
) -> None:
    if not concrete(obj.get(key)):
        errors.append(
            issue(
                "FIELD_REQUIRED", f"{path}.{key} must be concrete", path=f"{path}.{key}"
            )
        )


def require_list(
    obj: dict[str, Any], key: str, path: str, errors: list[dict[str, Any]]
) -> list[Any]:
    value = obj.get(key)
    if not isinstance(value, list) or not value:
        errors.append(
            issue(
                "LIST_REQUIRED",
                f"{path}.{key} must be a non-empty list",
                path=f"{path}.{key}",
            )
        )
        return []
    return value


def check_unique_ids(
    items: list[Any], path: str, errors: list[dict[str, Any]]
) -> set[str]:
    ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not concrete(item.get("id")):
            errors.append(
                issue(
                    "ID_REQUIRED",
                    f"{path}[{index}].id must be concrete",
                    path=f"{path}[{index}].id",
                )
            )
            continue
        item_id = item["id"]
        if item_id in ids:
            errors.append(
                issue("DUPLICATE_ID", f"duplicate id: {item_id}", id=item_id, path=path)
            )
        ids.add(item_id)
    return ids


def check_loops(loops: Any, errors: list[dict[str, Any]]) -> None:
    if not isinstance(loops, dict):
        errors.append(issue("LOOPS_REQUIRED", "loops must be an object"))
        return
    for loop_name in LOOPS:
        loop = loops.get(loop_name)
        if not isinstance(loop, dict):
            errors.append(
                issue("LOOP_REQUIRED", f"loops.{loop_name} must be an object")
            )
            continue
        for key in ("goal", "choice", "risk", "feedback", "reward", "next_constraint"):
            require_text(loop, key, f"loops.{loop_name}", errors)
        actions = require_list(loop, "actions", f"loops.{loop_name}", errors)
        for index, action in enumerate(actions):
            if not concrete(action):
                errors.append(
                    issue(
                        "ACTION_REQUIRED",
                        "loop actions must be concrete",
                        path=f"loops.{loop_name}.actions[{index}]",
                    )
                )


def check_dependencies(
    scope: list[Any], ids: set[str], errors: list[dict[str, Any]]
) -> None:
    graph: dict[str, list[str]] = {}
    buckets = {
        item.get("id"): item.get("bucket")
        for item in scope
        if isinstance(item, dict) and concrete(item.get("id"))
    }
    for index, item in enumerate(scope):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list):
            errors.append(
                issue(
                    "DEPENDENCIES_INVALID",
                    "dependencies must be a list",
                    path=f"scope[{index}].dependencies",
                )
            )
            continue
        graph[item_id] = dependencies
        for dependency in dependencies:
            if dependency not in ids:
                errors.append(
                    issue(
                        "UNKNOWN_DEPENDENCY",
                        f"unknown scope dependency: {dependency}",
                        path=f"scope[{index}].dependencies",
                    )
                )
            elif item.get("bucket") == "mvp" and buckets.get(dependency) in {
                "later",
                "cut",
            }:
                errors.append(
                    issue(
                        "MVP_DEPENDENCY",
                        f"mvp item cannot depend on {buckets[dependency]} item: {dependency}",
                        path=f"scope[{index}].dependencies",
                    )
                )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str) -> None:
        if item_id in visiting:
            errors.append(
                issue(
                    "SCOPE_CYCLE",
                    f"scope dependency cycle includes {item_id}",
                    id=item_id,
                )
            )
            return
        if item_id in visited:
            return
        visiting.add(item_id)
        for dependency in graph.get(item_id, []):
            if dependency in graph:
                visit(dependency)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in graph:
        visit(item_id)


def check_contract(
    project: Path, contract_path: Path, data: Any, require_approved: bool
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [issue("ROOT_INVALID", "contract root must be an object")]
    if data.get("schema_version") != 1:
        errors.append(issue("SCHEMA_VERSION", "schema_version must be 1"))

    project_data = data.get("project")
    if not isinstance(project_data, dict):
        errors.append(issue("PROJECT_REQUIRED", "project must be an object"))
    else:
        for key in ("experiment_id", "source_identity", "platform"):
            require_text(project_data, key, "project", errors)
        for key in ("hypothesis_revision", "project_revision"):
            if not isinstance(project_data.get(key), int) or project_data[key] < 1:
                errors.append(
                    issue(
                        "REVISION_REQUIRED", f"project.{key} must be a positive integer"
                    )
                )

    document = data.get("design_document")
    if not isinstance(document, dict):
        errors.append(issue("DOCUMENT_REQUIRED", "design_document must be an object"))
    else:
        path, path_error = relative_path(project, document.get("path"))
        if path_error:
            errors.append(
                issue("DOCUMENT_PATH", path_error, path="design_document.path")
            )
        if path:
            check_design_document(path, document.get("checksum"), errors)

    nucleus = data.get("design_nucleus")
    if not isinstance(nucleus, dict):
        errors.append(issue("NUCLEUS_REQUIRED", "design_nucleus must be an object"))
    else:
        for key in ("summary", "behavior_change", "differentiator"):
            require_text(nucleus, key, "design_nucleus", errors)
        evidence = nucleus.get("prototype_evidence_ids")
        if not isinstance(evidence, list):
            errors.append(
                issue("EVIDENCE_IDS_INVALID", "prototype_evidence_ids must be a list")
            )

    promise = data.get("player_promise")
    if not isinstance(promise, dict):
        errors.append(issue("PROMISE_REQUIRED", "player_promise must be an object"))
    else:
        for key in ("marketing", "first_10_minutes", "long_term"):
            require_text(promise, key, "player_promise", errors)
    check_loops(data.get("loops"), errors)

    scope = require_list(data, "scope", "root", errors)
    scope_ids = check_unique_ids(scope, "scope", errors)
    buckets: set[str] = set()
    for index, item in enumerate(scope):
        if not isinstance(item, dict):
            errors.append(
                issue(
                    "SCOPE_ITEM_INVALID",
                    "scope item must be an object",
                    path=f"scope[{index}]",
                )
            )
            continue
        bucket = item.get("bucket")
        if bucket not in BUCKETS:
            errors.append(
                issue(
                    "SCOPE_BUCKET",
                    f"invalid scope bucket: {bucket}",
                    path=f"scope[{index}].bucket",
                )
            )
        else:
            buckets.add(bucket)
        for key in ("name", "proves", "owner", "delete_condition"):
            require_text(item, key, f"scope[{index}]", errors)
        if not isinstance(item.get("dependencies", []), list):
            errors.append(
                issue(
                    "DEPENDENCIES_INVALID",
                    "scope dependencies must be a list",
                    path=f"scope[{index}].dependencies",
                )
            )
    if "mvp" not in buckets:
        errors.append(issue("MVP_MISSING", "scope must contain an mvp item"))
    if "vertical_slice" not in buckets:
        errors.append(
            issue("SLICE_MISSING", "scope must contain a vertical_slice item")
        )
    check_dependencies(scope, scope_ids, errors)

    systems = require_list(data, "systems", "root", errors)
    system_ids = check_unique_ids(systems, "systems", errors)
    for index, item in enumerate(systems):
        if not isinstance(item, dict):
            continue
        for key in (
            "name",
            "behavior_change",
            "feedback",
            "validation",
            "delete_condition",
        ):
            require_text(item, key, f"systems[{index}]", errors)
        if item.get("serves_loop") not in LOOPS:
            errors.append(
                issue(
                    "LOOP_REFERENCE",
                    "system serves_loop must be moment, session, or meta",
                    path=f"systems[{index}].serves_loop",
                )
            )
        if item.get("scope_id") not in scope_ids:
            errors.append(
                issue(
                    "SCOPE_REFERENCE",
                    "system scope_id must reference scope",
                    path=f"systems[{index}].scope_id",
                )
            )
        for key in ("inputs", "outputs"):
            require_list(item, key, f"systems[{index}]", errors)
    if not system_ids:
        errors.append(issue("SYSTEMS_EMPTY", "at least one system is required"))

    assumptions = require_list(data, "assumptions", "root", errors)
    assumption_ids = check_unique_ids(assumptions, "assumptions", errors)
    for index, item in enumerate(assumptions):
        if not isinstance(item, dict):
            continue
        for key in ("statement", "verification"):
            require_text(item, key, f"assumptions[{index}]", errors)
        if item.get("confidence") not in CONFIDENCE or item.get("impact") not in IMPACT:
            errors.append(
                issue(
                    "ASSUMPTION_RATING",
                    "assumption confidence and impact must be low, medium, or high",
                    path=f"assumptions[{index}]",
                )
            )
        if item.get("status") not in ASSUMPTION_STATUS:
            errors.append(
                issue(
                    "ASSUMPTION_STATUS",
                    "invalid assumption status",
                    path=f"assumptions[{index}].status",
                )
            )
        if not isinstance(item.get("evidence_ids", []), list):
            errors.append(
                issue(
                    "EVIDENCE_IDS_INVALID",
                    "assumption evidence_ids must be a list",
                    path=f"assumptions[{index}].evidence_ids",
                )
            )

    risks = require_list(data, "risks", "root", errors)
    check_unique_ids(risks, "risks", errors)
    for index, item in enumerate(risks):
        if not isinstance(item, dict):
            continue
        for key in ("cause", "impact", "mitigation", "trigger", "owner"):
            require_text(item, key, f"risks[{index}]", errors)

    validation = data.get("validation_plan")
    if not isinstance(validation, dict):
        errors.append(issue("VALIDATION_REQUIRED", "validation_plan must be an object"))
    else:
        for key in ("prototype", "next_investment_condition"):
            require_text(validation, key, "validation_plan", errors)
        for key in ("dangerous_assumption_ids", "pass_criteria", "fail_criteria"):
            require_list(validation, key, "validation_plan", errors)
        dangerous = validation.get("dangerous_assumption_ids", [])
        if isinstance(dangerous, list):
            for assumption_id in dangerous:
                if assumption_id not in assumption_ids:
                    errors.append(
                        issue(
                            "ASSUMPTION_REFERENCE",
                            f"unknown dangerous assumption: {assumption_id}",
                            path="validation_plan.dangerous_assumption_ids",
                        )
                    )

    approval = data.get("approval")
    if not isinstance(approval, dict) or approval.get("status") not in {
        "pending",
        "approved",
        "rejected",
    }:
        errors.append(
            issue(
                "APPROVAL_INVALID",
                "approval.status must be pending, approved, or rejected",
            )
        )
    elif approval.get("status") == "approved" or require_approved:
        if approval.get("status") != "approved":
            errors.append(issue("APPROVAL_PENDING", "explicit approval is required"))
        for key in ("approver_id", "approver_name", "rationale", "approved_at"):
            require_text(approval, key, "approval", errors)
        if concrete(approval.get("approved_at")):
            try:
                datetime.fromisoformat(approval["approved_at"])
            except ValueError:
                errors.append(
                    issue("APPROVAL_DATE", "approval.approved_at must be ISO-8601")
                )

    return errors


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    contract_path = args.contract.resolve()
    errors: list[dict[str, Any]] = []
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(issue("CONTRACT_READ", str(exc)))
        data = None
    if not errors:
        errors.extend(
            check_contract(project, contract_path, data, args.require_approved)
        )
    result = {"valid": not errors, "contract": str(contract_path), "errors": errors}
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print("INVALID")
        for item in errors:
            print(f"- {item['code']}: {item['message']}")
    else:
        print("VALID")
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
