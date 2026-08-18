from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import InvalidStateError, ToolUnavailableError
from .version import __version__

MARKER_NAME = ".loopforge-install.json"
IGNORED_NAMES = {"__pycache__", MARKER_NAME}


@dataclass(frozen=True, slots=True)
class InstallPlan:
    name: str
    source: Path
    destination: Path
    source_digest: str
    action: str
    reason: str
    keep_backup: bool = False


def bundled_skills_root() -> Path:
    packaged = Path(__file__).resolve().parent / "_bundled_skills"
    if packaged.is_dir():
        return packaged

    repository = Path(__file__).resolve().parents[2] / "skills"
    if repository.is_dir():
        return repository

    raise ToolUnavailableError(
        "Bundled Loopforge Skills are unavailable.",
        {
            "remediation": (
                "Reinstall Loopforge from an official wheel or a complete source clone."
            )
        },
    )


def codex_skills_root(explicit_root: Path | None = None) -> Path:
    if explicit_root is not None:
        return explicit_root.expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


def install_skills(
    *,
    host: str,
    explicit_root: Path | None,
    force: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if host != "codex":
        raise InvalidStateError(
            f"Unsupported Agent Skills host: {host}",
            "SKILL_HOST_UNSUPPORTED",
            {"host": host, "supported_hosts": ["codex"]},
        )

    source_root = bundled_skills_root()
    destination_root = codex_skills_root(explicit_root)
    sources = sorted(
        path for path in source_root.iterdir() if (path / "SKILL.md").is_file()
    )
    if not sources:
        raise ToolUnavailableError(
            "The Loopforge distribution contains no installable Skills.",
            {"source_root": str(source_root)},
        )

    plans = [
        plan_skill(source, destination_root / source.name, force=force)
        for source in sources
    ]
    result: dict[str, Any] = {
        "host": host,
        "tool_version": __version__,
        "skills_root": str(destination_root),
        "source": "bundled-distribution",
        "dry_run": dry_run,
        "skills": [plan_result(plan) for plan in plans],
        "installed": sum(plan.action == "install" for plan in plans),
        "updated": sum(plan.action == "update" for plan in plans),
        "skipped": sum(plan.action == "skip" for plan in plans),
    }
    if dry_run:
        return result

    destination_root.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".loopforge-setup-", dir=destination_root)
    )
    replacements: list[tuple[Path, Path | None, bool]] = []
    try:
        for plan in plans:
            if plan.action == "skip":
                continue
            staged = staging_root / plan.name
            shutil.copytree(
                plan.source,
                staged,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", MARKER_NAME),
            )
            write_marker(staged, plan.source_digest)

        for plan in plans:
            if plan.action == "skip":
                continue
            staged = staging_root / plan.name
            backup: Path | None = None
            if plan.destination.exists() or plan.destination.is_symlink():
                backup = available_backup_path(destination_root, plan.name)
                plan.destination.rename(backup)
            replacements.append((plan.destination, backup, plan.keep_backup))
            staged.rename(plan.destination)

    except Exception:
        for destination, backup, _ in reversed(replacements):
            remove_path(destination)
            if backup is not None and backup.exists():
                backup.rename(destination)
        raise
    finally:
        remove_path(staging_root)

    for _, backup, keep_backup in replacements:
        if backup is not None and not keep_backup:
            remove_path(backup)

    backups_by_name = {
        destination.name: backup
        for destination, backup, keep_backup in replacements
        if backup is not None and keep_backup
    }
    for item in result["skills"]:
        backup = backups_by_name.get(item["name"])
        if backup is not None:
            item["backup"] = str(backup)
    return result


def uninstall_skills(
    *,
    host: str,
    explicit_root: Path | None,
    force: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if host != "codex":
        raise InvalidStateError(
            f"Unsupported Agent Skills host: {host}",
            "SKILL_HOST_UNSUPPORTED",
            {"host": host, "supported_hosts": ["codex"]},
        )

    source_root = bundled_skills_root()
    destination_root = codex_skills_root(explicit_root)
    skill_names = sorted(
        path.name for path in source_root.iterdir() if (path / "SKILL.md").is_file()
    )
    plans = [
        plan_uninstall(name, destination_root / name, force=force)
        for name in skill_names
    ]
    result: dict[str, Any] = {
        "host": host,
        "tool_version": __version__,
        "skills_root": str(destination_root),
        "dry_run": dry_run,
        "skills": [plan_result(plan) for plan in plans],
        "removed": sum(plan.action == "uninstall" for plan in plans),
        "skipped": sum(plan.action == "skip" for plan in plans),
    }
    if dry_run or not destination_root.exists():
        return result

    removals: list[tuple[Path, Path, bool]] = []
    try:
        for plan in plans:
            if plan.action == "skip":
                continue
            backup = available_backup_path(destination_root, plan.name)
            plan.destination.rename(backup)
            removals.append((plan.destination, backup, plan.keep_backup))
    except Exception:
        for destination, backup, _ in reversed(removals):
            if backup.exists() or backup.is_symlink():
                backup.rename(destination)
        raise

    for _, backup, keep_backup in removals:
        if not keep_backup:
            remove_path(backup)
    backups_by_name = {
        destination.name: backup
        for destination, backup, keep_backup in removals
        if keep_backup
    }
    for item in result["skills"]:
        backup = backups_by_name.get(item["name"])
        if backup is not None:
            item["backup"] = str(backup)
    return result


def plan_skill(source: Path, destination: Path, *, force: bool) -> InstallPlan:
    source_digest = tree_digest(source)
    if not destination.exists() and not destination.is_symlink():
        return InstallPlan(
            source.name,
            source,
            destination,
            source_digest,
            "install",
            "not-installed",
        )

    if destination.is_symlink():
        try:
            existing_digest = tree_digest(destination.resolve())
        except (OSError, ValueError):
            existing_digest = "unreadable"
        if existing_digest == source_digest:
            return InstallPlan(
                source.name,
                source,
                destination,
                source_digest,
                "skip",
                "existing-identical-symlink",
            )
        if not force:
            raise skill_conflict(source.name, destination, "existing symlink differs")
        return InstallPlan(
            source.name,
            source,
            destination,
            source_digest,
            "update",
            "forced-symlink-replacement",
            keep_backup=True,
        )

    if not destination.is_dir():
        if not force:
            raise skill_conflict(
                source.name, destination, "destination is not a directory"
            )
        return InstallPlan(
            source.name,
            source,
            destination,
            source_digest,
            "update",
            "forced-file-replacement",
            keep_backup=True,
        )

    existing_digest = tree_digest(destination)
    if existing_digest == source_digest:
        return InstallPlan(
            source.name,
            source,
            destination,
            source_digest,
            "skip",
            "existing-identical",
        )

    marker = read_marker(destination)
    managed_digest = marker.get("installed_digest") if marker else None
    if managed_digest == existing_digest:
        return InstallPlan(
            source.name,
            source,
            destination,
            source_digest,
            "update",
            "managed-version-update",
        )
    if not force:
        reason = (
            "managed Skill has local changes"
            if marker
            else "unmanaged destination differs"
        )
        raise skill_conflict(source.name, destination, reason)
    return InstallPlan(
        source.name,
        source,
        destination,
        source_digest,
        "update",
        "forced-local-replacement",
        keep_backup=True,
    )


def plan_uninstall(name: str, destination: Path, *, force: bool) -> InstallPlan:
    if not destination.exists() and not destination.is_symlink():
        return InstallPlan(
            name,
            destination,
            destination,
            "missing",
            "skip",
            "not-installed",
        )
    if destination.is_symlink() or not destination.is_dir():
        if not force:
            raise uninstall_conflict(name, destination, "destination is not managed")
        return InstallPlan(
            name,
            destination,
            destination,
            "unmanaged",
            "uninstall",
            "forced-unmanaged-removal",
            keep_backup=True,
        )

    marker = read_marker(destination)
    if marker is None:
        if not force:
            raise uninstall_conflict(name, destination, "management marker is missing")
        return InstallPlan(
            name,
            destination,
            destination,
            tree_digest(destination),
            "uninstall",
            "forced-unmanaged-removal",
            keep_backup=True,
        )

    existing_digest = tree_digest(destination)
    if existing_digest == marker.get("installed_digest"):
        return InstallPlan(
            name,
            destination,
            destination,
            existing_digest,
            "uninstall",
            "managed-installation",
        )
    if not force:
        raise uninstall_conflict(name, destination, "managed Skill has local changes")
    return InstallPlan(
        name,
        destination,
        destination,
        existing_digest,
        "uninstall",
        "forced-modified-removal",
        keep_backup=True,
    )


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return "missing"
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            any(part in IGNORED_NAMES for part in relative.parts)
            or path.suffix == ".pyc"
        ):
            continue
        if path.is_symlink():
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0link\0")
            digest.update(os.readlink(path).encode("utf-8"))
            continue
        if not path.is_file():
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0file\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def read_marker(skill_root: Path) -> dict[str, Any] | None:
    marker = skill_root / MARKER_NAME
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if value.get("schema_version") != 1 or value.get("product") != "loopforge":
        return None
    return value


def write_marker(skill_root: Path, digest: str) -> None:
    marker = {
        "schema_version": 1,
        "product": "loopforge",
        "tool_version": __version__,
        "installed_digest": digest,
        "installed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    (skill_root / MARKER_NAME).write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def available_backup_path(root: Path, name: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    candidate = root / f"{name}.backup-{stamp}"
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = root / f"{name}.backup-{stamp}-{counter}"
        counter += 1
    return candidate


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def skill_conflict(name: str, destination: Path, reason: str) -> InvalidStateError:
    return InvalidStateError(
        f"Refusing to overwrite Skill '{name}': {reason}.",
        "SKILL_INSTALL_CONFLICT",
        {
            "skill": name,
            "destination": str(destination),
            "reason": reason,
            "remediation": (
                "Review the existing Skill, then rerun with --force to preserve it "
                "as a timestamped backup before replacement."
            ),
        },
    )


def uninstall_conflict(name: str, destination: Path, reason: str) -> InvalidStateError:
    return InvalidStateError(
        f"Refusing to uninstall Skill '{name}': {reason}.",
        "SKILL_UNINSTALL_CONFLICT",
        {
            "skill": name,
            "destination": str(destination),
            "reason": reason,
            "remediation": (
                "Review the existing Skill, then rerun with --force to preserve it "
                "as a timestamped backup instead of deleting it."
            ),
        },
    )


def plan_result(plan: InstallPlan) -> dict[str, Any]:
    return {
        "name": plan.name,
        "action": plan.action,
        "reason": plan.reason,
        "destination": str(plan.destination),
        "digest": plan.source_digest,
    }
