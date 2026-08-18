#!/usr/bin/env python3
"""Validate a direct-game-art manifest and its available runtime artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from datetime import date
from pathlib import Path
from typing import Any

PLACEHOLDER = re.compile(r"<[^<>]+>")
ASSET_STATUSES = {"planned", "raw", "curated", "runtime", "blocked"}
FORMATS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "glb"}
FAMILIES = {"character", "environment", "prop", "ui", "vfx", "animation"}
SOURCE_KINDS = {"human", "generated", "licensed", "public-domain", "derived"}
APPROVAL_STATUSES = {"pending", "approved", "rejected"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a game-art asset manifest.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args()


def issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": "error", "message": message, "details": details}


def nonempty(value: Any) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER.search(value)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def resolve_project_path(project: Path, raw: Any) -> tuple[Path | None, str | None]:
    if not nonempty(raw):
        return None, "path must be a concrete non-empty string"
    path = Path(raw)
    if path.is_absolute():
        return None, "path must be project-relative"
    resolved = (project / path).resolve()
    try:
        resolved.relative_to(project)
    except ValueError:
        return None, "path resolves outside the project"
    return resolved, None


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            return None
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            return None
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    return None


def raster_metadata(
    path: Path, asset_format: str
) -> tuple[tuple[int, int] | None, bool | None]:
    data = path.read_bytes()
    if asset_format == "png":
        if (
            len(data) < 26
            or not data.startswith(b"\x89PNG\r\n\x1a\n")
            or data[12:16] != b"IHDR"
        ):
            return None, None
        width, height = struct.unpack(">II", data[16:24])
        color_type = data[25]
        return (width, height), color_type in {4, 6} or b"tRNS" in data
    if asset_format == "gif":
        if len(data) < 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
            return None, None
        return struct.unpack("<HH", data[6:10]), None
    if asset_format in {"jpg", "jpeg"}:
        return jpeg_dimensions(data), False
    return None, None


def validate_approval(target: Any, require_approved: bool) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(target, dict):
        return [issue("TARGET_INVALID", "representative_target must be an object")]
    if not nonempty(target.get("id")):
        diagnostics.append(
            issue("TARGET_ID_INVALID", "representative target ID is required")
        )
    if not isinstance(target.get("revision"), int) or target["revision"] < 1:
        diagnostics.append(
            issue(
                "TARGET_REVISION_INVALID", "target revision must be a positive integer"
            )
        )
    approval = target.get("approval")
    if not isinstance(approval, dict):
        return diagnostics + [
            issue("TARGET_APPROVAL_INVALID", "target approval must be an object")
        ]
    status = approval.get("status")
    if status not in APPROVAL_STATUSES:
        diagnostics.append(
            issue(
                "TARGET_APPROVAL_INVALID",
                "target approval status is invalid",
                status=status,
            )
        )
    if require_approved and status != "approved":
        diagnostics.append(
            issue(
                "TARGET_NOT_APPROVED",
                "representative target approval is required",
                status=status,
            )
        )
    if status == "approved":
        for field in ("approver_id", "approver_name", "rationale"):
            if not nonempty(approval.get(field)):
                diagnostics.append(
                    issue(
                        "TARGET_APPROVAL_INCOMPLETE",
                        f"approved target requires {field}",
                        field=field,
                    )
                )
    return diagnostics


def validate_asset(
    project: Path, asset: Any, index: int
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(asset, dict):
        return (
            [issue("ASSET_INVALID", "asset entry must be an object", index=index)],
            None,
            [],
        )
    asset_id = asset.get("id") if nonempty(asset.get("id")) else None
    label = asset_id or f"index:{index}"
    if asset_id is None:
        diagnostics.append(
            issue("ASSET_ID_INVALID", "asset ID is required", asset=label)
        )
    if asset.get("family") not in FAMILIES:
        diagnostics.append(
            issue(
                "ASSET_FAMILY_INVALID",
                "asset family is invalid",
                asset=label,
                family=asset.get("family"),
            )
        )
    if not nonempty(asset.get("role")):
        diagnostics.append(
            issue("ASSET_ROLE_INVALID", "asset role is required", asset=label)
        )
    status = asset.get("status")
    if status not in ASSET_STATUSES:
        diagnostics.append(
            issue(
                "ASSET_STATUS_INVALID",
                "asset status is invalid",
                asset=label,
                status=status,
            )
        )
    asset_format = asset.get("format")
    if asset_format not in FORMATS:
        diagnostics.append(
            issue(
                "ASSET_FORMAT_INVALID",
                "asset format is unsupported",
                asset=label,
                format=asset_format,
            )
        )
    alpha = asset.get("alpha")
    if alpha not in {"required", "opaque", "optional"}:
        diagnostics.append(
            issue(
                "ASSET_ALPHA_INVALID",
                "alpha must be required, opaque, or optional",
                asset=label,
            )
        )
    dimensions = asset.get("dimensions")
    declared_dimensions: tuple[int, int] | None = None
    if isinstance(dimensions, dict) and all(
        isinstance(dimensions.get(key), int) and dimensions[key] > 0
        for key in ("width", "height")
    ):
        declared_dimensions = dimensions["width"], dimensions["height"]
    else:
        diagnostics.append(
            issue(
                "ASSET_DIMENSIONS_INVALID",
                "positive integer width and height are required",
                asset=label,
            )
        )
    max_bytes = asset.get("max_bytes")
    if not isinstance(max_bytes, int) or max_bytes < 1:
        diagnostics.append(
            issue(
                "ASSET_BUDGET_INVALID",
                "max_bytes must be a positive integer",
                asset=label,
            )
        )
    if not isinstance(asset.get("variants"), list):
        diagnostics.append(
            issue("ASSET_VARIANTS_INVALID", "variants must be a list", asset=label)
        )

    runtime = asset.get("runtime")
    if not isinstance(runtime, dict):
        diagnostics.append(
            issue(
                "ASSET_RUNTIME_INVALID",
                "runtime contract must be an object",
                asset=label,
            )
        )
    else:
        for field in ("display_size", "pivot"):
            if not nonempty(runtime.get(field)):
                diagnostics.append(
                    issue(
                        "ASSET_RUNTIME_INVALID",
                        f"runtime {field} is required",
                        asset=label,
                        field=field,
                    )
                )
        frames, fps, loop = (
            runtime.get("frames"),
            runtime.get("fps"),
            runtime.get("loop"),
        )
        if not isinstance(frames, int) or frames < 1:
            diagnostics.append(
                issue(
                    "ASSET_RUNTIME_INVALID",
                    "runtime frames must be a positive integer",
                    asset=label,
                )
            )
        if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps < 0:
            diagnostics.append(
                issue(
                    "ASSET_RUNTIME_INVALID",
                    "runtime fps must be non-negative",
                    asset=label,
                )
            )
        elif isinstance(frames, int) and frames > 1 and fps <= 0:
            diagnostics.append(
                issue(
                    "ASSET_RUNTIME_INVALID",
                    "animated assets require fps greater than zero",
                    asset=label,
                )
            )
        if not isinstance(loop, bool):
            diagnostics.append(
                issue(
                    "ASSET_RUNTIME_INVALID", "runtime loop must be boolean", asset=label
                )
            )

    provenance = asset.get("provenance")
    parent_ids: list[str] = []
    if not isinstance(provenance, dict):
        diagnostics.append(
            issue(
                "ASSET_PROVENANCE_INVALID", "provenance must be an object", asset=label
            )
        )
    else:
        if provenance.get("source_kind") not in SOURCE_KINDS:
            diagnostics.append(
                issue("ASSET_PROVENANCE_INVALID", "source_kind is invalid", asset=label)
            )
        for field in (
            "source_uri",
            "creator_or_provider",
            "model_or_version",
            "license",
        ):
            if not nonempty(provenance.get(field)):
                diagnostics.append(
                    issue(
                        "ASSET_PROVENANCE_INVALID",
                        f"provenance {field} is required",
                        asset=label,
                        field=field,
                    )
                )
        acquired_at = provenance.get("acquired_at")
        try:
            date.fromisoformat(acquired_at)
        except (TypeError, ValueError):
            diagnostics.append(
                issue(
                    "ASSET_PROVENANCE_INVALID",
                    "acquired_at must be an ISO-8601 date",
                    asset=label,
                )
            )
        parent_ids_value = provenance.get("parent_asset_ids")
        if isinstance(parent_ids_value, list) and all(
            nonempty(item) for item in parent_ids_value
        ):
            parent_ids = parent_ids_value
        else:
            diagnostics.append(
                issue(
                    "ASSET_PROVENANCE_INVALID",
                    "parent_asset_ids must be a list of IDs",
                    asset=label,
                )
            )
        if not isinstance(provenance.get("transformations"), list):
            diagnostics.append(
                issue(
                    "ASSET_PROVENANCE_INVALID",
                    "transformations must be a list",
                    asset=label,
                )
            )

    resolved: dict[str, Path] = {}
    for field in ("source_path", "curated_path", "runtime_path"):
        path, error = resolve_project_path(project, asset.get(field))
        if error:
            diagnostics.append(
                issue(
                    "ASSET_PATH_INVALID",
                    error,
                    asset=label,
                    field=field,
                    path=asset.get(field),
                )
            )
        elif path is not None:
            resolved[field] = path

    required_paths = {
        "raw": ("source_path",),
        "curated": ("source_path", "curated_path"),
        "runtime": ("source_path", "curated_path", "runtime_path"),
    }
    for field in required_paths.get(status, ()):
        path = resolved.get(field)
        if path is not None and not path.is_file():
            diagnostics.append(
                issue(
                    "ASSET_FILE_MISSING",
                    "required asset file does not exist",
                    asset=label,
                    field=field,
                    path=str(path),
                )
            )

    runtime_path = resolved.get("runtime_path")
    if runtime_path is not None and runtime_path.is_file() and status == "runtime":
        expected_suffix = ".jpg" if asset_format == "jpeg" else f".{asset_format}"
        if runtime_path.suffix.lower() not in (
            {".jpg", ".jpeg"} if asset_format in {"jpg", "jpeg"} else {expected_suffix}
        ):
            diagnostics.append(
                issue(
                    "ASSET_FORMAT_MISMATCH",
                    "runtime file extension does not match format",
                    asset=label,
                    path=str(runtime_path),
                )
            )
        if isinstance(max_bytes, int) and runtime_path.stat().st_size > max_bytes:
            diagnostics.append(
                issue(
                    "ASSET_SIZE_EXCEEDED",
                    "runtime file exceeds max_bytes",
                    asset=label,
                    actual=runtime_path.stat().st_size,
                    maximum=max_bytes,
                )
            )
        actual_dimensions, actual_alpha = raster_metadata(runtime_path, asset_format)
        if asset_format in {"png", "jpg", "jpeg", "gif"} and actual_dimensions is None:
            diagnostics.append(
                issue(
                    "ASSET_FILE_INVALID",
                    "runtime raster header is invalid",
                    asset=label,
                    path=str(runtime_path),
                )
            )
        elif actual_dimensions is not None and declared_dimensions != actual_dimensions:
            diagnostics.append(
                issue(
                    "ASSET_DIMENSIONS_MISMATCH",
                    "runtime dimensions do not match manifest",
                    asset=label,
                    declared=declared_dimensions,
                    actual=actual_dimensions,
                )
            )
        if alpha == "required" and actual_alpha is False:
            diagnostics.append(
                issue(
                    "ASSET_ALPHA_MISSING", "runtime asset requires alpha", asset=label
                )
            )
        checksum = asset.get("checksum")
        if not nonempty(checksum):
            diagnostics.append(
                issue(
                    "ASSET_CHECKSUM_MISSING",
                    "runtime asset checksum is required",
                    asset=label,
                )
            )
        else:
            actual_checksum = sha256(runtime_path)
            if checksum != actual_checksum:
                diagnostics.append(
                    issue(
                        "ASSET_CHECKSUM_MISMATCH",
                        "runtime asset checksum does not match",
                        asset=label,
                        declared=checksum,
                        actual=actual_checksum,
                    )
                )
    return diagnostics, asset_id, parent_ids


def validate(
    project: Path, manifest_path: Path, require_approved: bool
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    project = project.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    if not project.is_dir():
        return {
            "project": str(project),
            "manifest": str(manifest_path),
            "diagnostics": [issue("PROJECT_MISSING", "project root does not exist")],
        }
    try:
        manifest_path.relative_to(project)
    except ValueError:
        diagnostics.append(
            issue("MANIFEST_OUTSIDE_PROJECT", "manifest must remain inside the project")
        )
    if not manifest_path.is_file():
        diagnostics.append(issue("MANIFEST_MISSING", "manifest file does not exist"))
        return {
            "project": str(project),
            "manifest": str(manifest_path),
            "diagnostics": diagnostics,
        }
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        diagnostics.append(
            issue(
                "MANIFEST_INVALID_JSON",
                "manifest is not readable valid JSON",
                cause=str(exc),
            )
        )
        return {
            "project": str(project),
            "manifest": str(manifest_path),
            "diagnostics": diagnostics,
        }
    if not isinstance(document, dict):
        diagnostics.append(issue("MANIFEST_INVALID", "manifest must be a JSON object"))
        return {
            "project": str(project),
            "manifest": str(manifest_path),
            "diagnostics": diagnostics,
        }
    if PLACEHOLDER.search(json.dumps(document, sort_keys=True)):
        diagnostics.append(
            issue(
                "MANIFEST_PLACEHOLDERS_REMAIN",
                "replace all template placeholders before validation",
            )
        )
    if document.get("schema_version") != 1:
        diagnostics.append(
            issue(
                "MANIFEST_SCHEMA_UNSUPPORTED",
                "schema_version must be 1",
                schema_version=document.get("schema_version"),
            )
        )
    if not nonempty(document.get("project_identity")):
        diagnostics.append(
            issue("PROJECT_IDENTITY_INVALID", "project_identity is required")
        )
    diagnostics.extend(
        validate_approval(document.get("representative_target"), require_approved)
    )
    assets = document.get("assets")
    if not isinstance(assets, list) or not assets:
        diagnostics.append(issue("ASSETS_INVALID", "assets must be a non-empty list"))
    else:
        ids: list[str] = []
        parents: list[tuple[str, str]] = []
        for index, asset in enumerate(assets):
            asset_diagnostics, asset_id, parent_ids = validate_asset(
                project, asset, index
            )
            diagnostics.extend(asset_diagnostics)
            if asset_id is not None:
                ids.append(asset_id)
                parents.extend((asset_id, parent) for parent in parent_ids)
        duplicates = sorted({asset_id for asset_id in ids if ids.count(asset_id) > 1})
        if duplicates:
            diagnostics.append(
                issue("ASSET_IDS_DUPLICATE", "asset IDs must be unique", ids=duplicates)
            )
        known_ids = set(ids)
        for asset_id, parent in parents:
            if parent not in known_ids:
                diagnostics.append(
                    issue(
                        "ASSET_PARENT_UNKNOWN",
                        "parent asset ID is not present in manifest",
                        asset=asset_id,
                        parent=parent,
                    )
                )
    return {
        "project": str(project),
        "manifest": str(manifest_path),
        "diagnostics": diagnostics,
    }


def emit(result: dict[str, Any], output_format: str) -> None:
    ok = not result["diagnostics"]
    payload = {"schema_version": 1, "ok": ok, **result}
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True))
        return
    stream = sys.stdout if ok else sys.stderr
    if ok:
        print(f"valid: {result['manifest']}", file=stream)
    else:
        for diagnostic in result["diagnostics"]:
            print(f"ERROR {diagnostic['code']}: {diagnostic['message']}", file=stream)


def main() -> int:
    arguments = parse_args()
    result = validate(arguments.project, arguments.manifest, arguments.require_approved)
    emit(result, arguments.format)
    return 0 if not result["diagnostics"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
