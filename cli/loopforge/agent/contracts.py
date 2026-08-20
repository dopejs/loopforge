from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..project import LoopforgeProject

CONTEXT_SCHEMA = "game-project-context-v1"


def project_id(root: Path) -> str:
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:24]
    return f"gameproj_{digest}"


def build_project_context(project: LoopforgeProject) -> dict[str, Any]:
    inspected = project.inspect()
    if project.store.initialized:
        status = project.status()
        observed_revision = int(status["observed_revision"])
        stage = str(status["stage"])
        next_actions = list(status.get("next_allowed_actions", []))
    else:
        observed_revision = 0
        stage = "UNINITIALIZED"
        next_actions = ["init"]

    engine = None
    if inspected["engine_detections"]:
        engine = inspected["engine_detections"][0]["engine"]
    capabilities = [
        "loopforge.project_context",
        "loopforge.status",
        "loopforge.evidence",
    ]
    if inspected["executables"].get("godot"):
        capabilities.extend(["godot.build", "godot.test", "godot.capture"])
    return {
        "schema_version": CONTEXT_SCHEMA,
        "project_id": project_id(project.root),
        "project_root": str(project.root),
        "observed_revision": observed_revision,
        "stage": stage,
        "engine": engine,
        "capabilities": sorted(set(capabilities)),
        "next_actions": next_actions,
        "redactions": [
            "environment_variables",
            "provider_credentials",
            "access_tokens",
        ],
    }
