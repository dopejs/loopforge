"""Engine run history, read from the project's deterministic core.

`LoopforgeProject.run_engine` writes one record per build or test run under
`.loopforge/runs/`. Those records are the data behind both the Terminal and
Test workspaces -- the same source viewed two ways -- so the projection lives
here rather than being duplicated per surface.

Kura's `/v1/runs` is a different concept (its own workflow runs) and is empty
for this purpose; engine runs are Loopforge's, as `docs/architecture.md`
assigns build and test adapters to the core layer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RUN_SCHEMA = "loopforge-run-v1"
MAX_RUNS = 200
#: Process output can be megabytes. The list view never needs it, and the
#: detail view is bounded so one runaway run cannot exhaust the UI.
MAX_OUTPUT_CHARS = 200_000

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: `run_engine` writes these; anything else is from a future core version.
_KNOWN_STATUSES = {"completed", "failed", "interrupted"}


def _truncate(value: object) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    kept = text[-MAX_OUTPUT_CHARS:]
    return f"… [{len(text) - MAX_OUTPUT_CHARS} characters truncated]\n{kept}"


class RunStore:
    """Reads engine run records. Read-only: runs are written by the core."""

    def __init__(self, project_root: Path) -> None:
        self.directory = project_root / ".loopforge" / "runs"

    def list(self, operation: str | None = None) -> list[dict[str, Any]]:
        """Runs, newest first, without their output.

        An unreadable record is skipped rather than failing the listing: one
        bad file must not hide the run history.
        """
        if not self.directory.is_dir():
            return []
        runs = []
        for path in self.directory.glob("*.json"):
            record = self._read(path)
            if record is None:
                continue
            if operation is not None and record.get("operation") != operation:
                continue
            runs.append(self._summary(record))
        runs.sort(key=lambda item: item["started_at"], reverse=True)
        return runs[:MAX_RUNS]

    def read(self, run_id: str) -> dict[str, Any] | None:
        """One run, including its bounded output."""
        if not _SAFE_ID.match(run_id or ""):
            return None
        record = self._read(self.directory / f"{run_id}.json")
        if record is None:
            return None
        detail = self._summary(record)
        detail["stdout"] = _truncate(record.get("stdout"))
        detail["stderr"] = _truncate(record.get("stderr"))
        detail["command"] = [str(part) for part in record.get("command") or []]
        return detail

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        status = record.get("status")
        exit_code = record.get("exit_code")
        return {
            "id": str(record.get("run_id") or ""),
            "operation": str(record.get("operation") or ""),
            "adapter": str(record.get("adapter") or ""),
            "adapter_version": str(record.get("adapter_version") or ""),
            # An unrecognized status is surfaced as unknown rather than being
            # coerced into "failed", which would misreport a newer core.
            "status": status if status in _KNOWN_STATUSES else "unknown",
            "exit_code": exit_code if isinstance(exit_code, int) else None,
            "timed_out": record.get("timed_out") is True,
            "started_at": str(record.get("started_at") or ""),
            "finished_at": str(record.get("finished_at") or ""),
        }

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(record, dict) or not isinstance(record.get("run_id"), str):
            return None
        return record
