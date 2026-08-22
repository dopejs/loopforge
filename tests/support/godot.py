"""A real Godot project for exercising the engine adapter.

`LoopforgeProject.run_engine` spawns a Godot binary, reads its exit code and
registers evidence from the result. Until now nothing tested it: the only
Godot-related test substituted a shell script that echoed a version string, so
the adapter's actual contract with the engine -- that `--headless --quit` boots
the main scene, that a non-zero exit becomes failed evidence, that a build and
a test together satisfy a claim -- was never executed.

That is the same gap mocked tests left in the Kura client, where every
wire-level failure passed the unit suite and surfaced only against a live
daemon. This module is the engine-side equivalent of `kura_daemon`.

Skipped when no Godot binary is available, so a developer without one still
gets a green run; CI installs Godot and fails loudly if it goes missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "godot"

#: Environment variable the fixture scene reads to choose its exit code, which
#: is how the failure path is driven through a real engine run.
EXIT_CODE_VARIABLE = "LOOPFORGE_FIXTURE_EXIT_CODE"


def _publish_override_on_path() -> None:
    """Make an overridden binary reachable the way the adapter reaches it.

    `run_engine` resolves Godot through PATH and knows nothing about
    LOOPFORGE_GODOT_BIN. Without this, setting only the override would leave
    the tests un-skipped while the adapter still could not find an engine --
    they would fail, and for the wrong reason. Linking the override onto PATH
    keeps the skip condition and the code under test looking at one binary.
    """
    override = os.environ.get("LOOPFORGE_GODOT_BIN")
    if not override or not Path(override).is_file():
        return
    if shutil.which("godot4") or shutil.which("godot"):
        return
    shim = Path(tempfile.mkdtemp(prefix="loopforge-godot-shim-")) / "godot4"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.symlink_to(override)
    os.environ["PATH"] = f"{shim.parent}{os.pathsep}{os.environ.get('PATH', '')}"


_publish_override_on_path()


def godot_binary() -> str | None:
    """Locate the binary the adapter will use.

    Deliberately PATH-only, matching `run_engine`. The override is honoured by
    having been placed on PATH above, not by being consulted here.
    """
    return shutil.which("godot4") or shutil.which("godot")


def godot_major_version(binary: str) -> int | None:
    """Read the reported major version, or None when it cannot be determined.

    A Godot 3 binary would fail the adapter's own doctor check, so tests must
    not run against one and silently report a different product's behaviour.
    """
    try:
        completed = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip()
    head = text.split(".", 1)[0].strip()
    return int(head) if head.isdigit() else None


def _usable_godot() -> bool:
    binary = godot_binary()
    return binary is not None and godot_major_version(binary) == 4


requires_godot = unittest.skipUnless(
    _usable_godot(),
    "needs a Godot 4 binary: install it or set LOOPFORGE_GODOT_BIN",
)


def materialize_fixture() -> Path:
    """Copy the fixture project into a fresh temporary directory.

    Never run in place: the adapter writes `.loopforge/` state and Godot writes
    an imported-asset cache, so running against the checked-out fixture would
    both dirty the tree and let one test observe another's state.
    """
    destination = Path(tempfile.mkdtemp(prefix="loopforge-godot-")) / "project"
    shutil.copytree(FIXTURE_ROOT, destination)
    return destination
