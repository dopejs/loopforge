from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..project import LoopforgeProject

CONTEXT_SCHEMA = "game-project-context-v1"


def provisional_project_id(root: Path) -> str:
    """A name for a directory that is not a Loopforge project yet.

    Derived from the path because there is nothing else to derive it from: the
    real id is minted at `init` and lives in the event history. Used only
    before that point, and it changes if the directory is moved -- which is
    why it must not outlive initialization.
    """
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:24]
    return f"gameproj_{digest}"


def build_project_context(project: LoopforgeProject) -> dict[str, Any]:
    inspected = project.inspect()
    if project.store.initialized:
        status = project.status()
        observed_revision = int(status["observed_revision"])
        stage = str(status["stage"])
        next_actions = list(status.get("next_allowed_actions", []))
        # The id the event history and every integrity check use.
        #
        # This reported a hash of the path instead, so an agent told the user
        # a `gameproj_...` that no command would ever print -- `status` did not
        # expose any id at all, and `history` printed the other one. Anyone who
        # took the id from the conversation and looked it up found nothing.
        identifier = str(status["project_id"])
    else:
        observed_revision = 0
        stage = "UNINITIALIZED"
        next_actions = ["init"]
        # Nothing has been minted yet; the path is all there is to name it by.
        identifier = provisional_project_id(project.root)

    # What the project was initialized as, falling back to what is detectable
    # now. The recorded value is the one the rest of the system agrees on;
    # detection is what an uninitialized directory has instead.
    engine = None
    if project.store.initialized:
        engine = project.store.read_project_config().get("engine")
    if engine is None and inspected["engine_detections"]:
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
        "project_id": identifier,
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
