from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import InvalidStateError, NotInitializedError, StateConflictError
from .jsonutil import (
    atomic_write_json,
    canonical_json_bytes,
    load_json_file,
    sha256_bytes,
)
from .locking import ProjectLock
from .version import __version__

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class EventStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = self.project_root / ".loopforge"
        self.project_file = self.state_dir / "project.json"
        self.events_file = self.state_dir / "events.jsonl"
        self.state_file = self.state_dir / "state.json"
        self.lock_file = self.state_dir / "lock"

    @property
    def initialized(self) -> bool:
        return self.project_file.is_file() and self.events_file.is_file()

    def initialize(self, engine: str | None = None) -> tuple[dict[str, Any], bool]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with ProjectLock(self.lock_file):
            if self.events_file.exists():
                if not self.project_file.exists():
                    raise InvalidStateError(
                        "Event history exists without project configuration.",
                        "PROJECT_CONFIG_MISSING",
                    )
                events = self.read_events()
                if not events:
                    raise InvalidStateError(
                        "Event history exists but contains no initialization event.",
                        "INITIALIZATION_EVENT_MISSING",
                    )
                state = project_events(events)
                return state, False

            if self.project_file.exists():
                config = self._validate_project_config(
                    load_json_file(self.project_file)
                )
            else:
                config = {
                    "schema_version": SCHEMA_VERSION,
                    "project_id": opaque_id("prj"),
                    # What was detected in the directory, not a placeholder.
                    #
                    # This was written as null and never written again -- the
                    # only write to this file is the one below. So the schema
                    # advertised an engine the product had no way to fill, and
                    # a surface reading it saw "no engine" for a Godot project
                    # sitting right there. An agent looking at that asked the
                    # user which engine they wanted, a question nothing could
                    # act on.
                    "engine": engine,
                    "target_platforms": [],
                    "profiles": {},
                }
                atomic_write_json(self.project_file, config)

            event = self._new_event(
                revision=1,
                previous_event_hash=None,
                event_type="project.initialized",
                payload={
                    "project_id": config["project_id"],
                    "experiment_id": opaque_id("exp"),
                    "stage": "DISCOVERY",
                },
            )
            self._append_event(event)
            state = project_events([event])
            atomic_write_json(self.state_file, state)
            return state, True

    def read_project_config(self) -> dict[str, Any]:
        if not self.project_file.exists():
            raise NotInitializedError(str(self.project_root))
        return self._validate_project_config(load_json_file(self.project_file))

    def read_events(self) -> list[dict[str, Any]]:
        try:
            raw = self.events_file.read_bytes()
        except FileNotFoundError as exc:
            raise NotInitializedError(str(self.project_root)) from exc
        except OSError as exc:
            raise InvalidStateError(
                "Cannot read the project event log.",
                "EVENT_LOG_UNREADABLE",
                {"path": str(self.events_file), "cause": str(exc)},
            ) from exc

        if raw and not raw.endswith(b"\n"):
            raise InvalidStateError(
                "The event log has an incomplete final record.",
                "EVENT_LOG_TORN_WRITE",
                {"path": str(self.events_file)},
            )

        events: list[dict[str, Any]] = []
        previous_hash: str | None = None
        for line_number, raw_line in enumerate(raw.splitlines(), start=1):
            try:
                event = json.loads(raw_line)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise InvalidStateError(
                    f"Event log line {line_number} is invalid JSON.",
                    "EVENT_LOG_INVALID_JSON",
                    {"line": line_number, "cause": str(exc)},
                ) from exc
            if not isinstance(event, dict):
                raise InvalidStateError(
                    f"Event log line {line_number} is not an object.",
                    "EVENT_LOG_INVALID_EVENT",
                    {"line": line_number},
                )
            self._validate_event(event, line_number, previous_hash)
            events.append(event)
            previous_hash = event["event_hash"]
        return events

    def current_state(self) -> tuple[dict[str, Any], str]:
        events = self.read_events()
        if not events:
            raise InvalidStateError(
                "The project has no initialization event.",
                "INITIALIZATION_EVENT_MISSING",
            )
        projected = project_events(events)
        snapshot_status = self._snapshot_status(projected)
        return projected, snapshot_status

    def commit(
        self,
        event_type: str,
        payload: dict[str, Any],
        expected_revision: int | None,
        run_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.initialized:
            raise NotInitializedError(str(self.project_root))
        with ProjectLock(self.lock_file):
            events = self.read_events()
            state = project_events(events)
            current_revision = state["revision"]
            if expected_revision is not None and expected_revision != current_revision:
                raise StateConflictError(
                    "The project changed after the caller observed it.",
                    "EXPECTED_REVISION_MISMATCH",
                    {
                        "expected_revision": expected_revision,
                        "actual_revision": current_revision,
                    },
                )

            event = self._new_event(
                revision=current_revision + 1,
                previous_event_hash=events[-1]["event_hash"],
                event_type=event_type,
                payload=payload,
                run_id=run_id,
            )
            self._append_event(event)
            new_state = project_events([*events, event])
            atomic_write_json(self.state_file, new_state)
            return event, new_state

    def reconcile(self, apply: bool) -> dict[str, Any]:
        if not self.initialized:
            raise NotInitializedError(str(self.project_root))
        with ProjectLock(self.lock_file):
            events = self.read_events()
            projected = project_events(events)
            status = self._snapshot_status(projected)
            actions: list[dict[str, Any]] = []
            if status != "current":
                actions.append(
                    {
                        "action": "rebuild_state_snapshot",
                        "from_status": status,
                        "target_revision": projected["revision"],
                    }
                )
            if apply and actions:
                atomic_write_json(self.state_file, projected)
            return {
                "applied": apply,
                "actions": actions,
                "observed_revision": projected["revision"],
                "snapshot_status": "current" if apply and actions else status,
            }

    def _new_event(
        self,
        revision: int,
        previous_event_hash: str | None,
        event_type: str,
        payload: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": opaque_id("evt"),
            "revision": revision,
            "event_type": event_type,
            "occurred_at": utc_now(),
            "previous_event_hash": previous_event_hash,
            "run_id": run_id,
            "producer": {
                "name": "loopforge",
                "version": __version__,
            },
            "payload": payload,
        }
        event["event_hash"] = sha256_bytes(canonical_json_bytes(event))
        return event

    def _append_event(self, event: dict[str, Any]) -> None:
        payload = canonical_json_bytes(event) + b"\n"
        descriptor = os.open(
            self.events_file,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise InvalidStateError(
                    "The event log write was incomplete.",
                    "EVENT_LOG_SHORT_WRITE",
                    {"expected_bytes": len(payload), "written_bytes": written},
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _validate_event(
        self,
        event: dict[str, Any],
        line_number: int,
        expected_previous_hash: str | None,
    ) -> None:
        required = {
            "schema_version",
            "event_id",
            "revision",
            "event_type",
            "occurred_at",
            "previous_event_hash",
            "producer",
            "payload",
            "event_hash",
        }
        missing = sorted(required - event.keys())
        if missing:
            raise InvalidStateError(
                f"Event log line {line_number} is missing required fields.",
                "EVENT_LOG_INVALID_EVENT",
                {"line": line_number, "missing": missing},
            )
        if event["schema_version"] != SCHEMA_VERSION:
            raise InvalidStateError(
                f"Unsupported event schema version on line {line_number}.",
                "UNKNOWN_SCHEMA_VERSION",
                {"line": line_number, "schema_version": event["schema_version"]},
            )
        if not isinstance(event["revision"], int) or isinstance(
            event["revision"], bool
        ):
            raise InvalidStateError(
                f"Event revision is not an integer on line {line_number}.",
                "EVENT_REVISION_INVALID",
                {"line": line_number},
            )
        if not isinstance(event["event_type"], str) or not isinstance(
            event["payload"], dict
        ):
            raise InvalidStateError(
                f"Event type or payload is invalid on line {line_number}.",
                "EVENT_LOG_INVALID_EVENT",
                {"line": line_number},
            )
        if not isinstance(event["revision"], int) or isinstance(
            event["revision"], bool
        ):
            raise InvalidStateError(
                f"Event revision is not an integer on line {line_number}.",
                "EVENT_REVISION_INVALID",
                {"line": line_number},
            )
        if event["revision"] != line_number:
            raise InvalidStateError(
                f"Event revision is not contiguous on line {line_number}.",
                "EVENT_REVISION_INVALID",
                {"line": line_number, "revision": event["revision"]},
            )
        if event["previous_event_hash"] != expected_previous_hash:
            raise InvalidStateError(
                f"Event hash chain is broken on line {line_number}.",
                "EVENT_HASH_CHAIN_BROKEN",
                {"line": line_number},
            )
        unhashed = {key: value for key, value in event.items() if key != "event_hash"}
        actual_hash = sha256_bytes(canonical_json_bytes(unhashed))
        if event["event_hash"] != actual_hash:
            raise InvalidStateError(
                f"Event checksum is invalid on line {line_number}.",
                "EVENT_HASH_INVALID",
                {"line": line_number},
            )

        payload = event["payload"]
        if event["event_type"] == "project.initialized":
            required_payload = {"project_id", "experiment_id", "stage"}
        elif event["event_type"] == "evidence.registered":
            required_payload = {"evidence"}
        elif event["event_type"] == "hypothesis.created":
            required_payload = {"hypothesis"}
        elif event["event_type"] == "playtest.protocol.created":
            required_payload = {"protocol"}
        elif event["event_type"] == "decision.recorded":
            required_payload = {"decision"}
        elif event["event_type"] == "stage.transitioned":
            required_payload = {"from", "to"}
        else:
            required_payload = set()
        missing_payload = sorted(required_payload - payload.keys())
        if missing_payload:
            raise InvalidStateError(
                f"Event payload is incomplete on line {line_number}.",
                "EVENT_PAYLOAD_INVALID",
                {"line": line_number, "missing": missing_payload},
            )

    def _validate_project_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if config.get("schema_version") != SCHEMA_VERSION:
            raise InvalidStateError(
                "Unsupported project schema version.",
                "UNKNOWN_SCHEMA_VERSION",
                {"schema_version": config.get("schema_version")},
            )
        if not isinstance(config.get("project_id"), str) or not config["project_id"]:
            raise InvalidStateError(
                "Project configuration has no valid project ID.",
                "PROJECT_ID_INVALID",
            )
        return config

    def _snapshot_status(self, projected: dict[str, Any]) -> str:
        if not self.state_file.exists():
            return "missing"
        try:
            snapshot = load_json_file(self.state_file)
        except InvalidStateError:
            return "invalid"
        return "current" if snapshot == projected else "stale"


def project_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] | None = None
    evidence_count = 0
    for event in events:
        event_type = event["event_type"]
        payload = event["payload"]
        if event_type == "project.initialized":
            if not all(
                isinstance(payload.get(key), str) and payload[key]
                for key in ("project_id", "experiment_id", "stage")
            ):
                raise InvalidStateError(
                    "Initialization payload contains invalid identifiers.",
                    "EVENT_PAYLOAD_INVALID",
                    {"event_id": event["event_id"]},
                )
            if state is not None:
                raise InvalidStateError(
                    "The event log contains more than one initialization event.",
                    "DUPLICATE_INITIALIZATION_EVENT",
                )
            state = {
                "schema_version": SCHEMA_VERSION,
                "project_id": payload["project_id"],
                "revision": event["revision"],
                "stage": payload["stage"],
                "active_experiment": {
                    "experiment_id": payload["experiment_id"],
                    "hypothesis_id": None,
                    "hypothesis_revision": None,
                    "hypothesis_approval": None,
                },
                "evidence_count": 0,
                "last_event_id": event["event_id"],
                "last_event_hash": event["event_hash"],
            }
            continue
        if state is None:
            raise InvalidStateError(
                "The first event is not project initialization.",
                "INITIALIZATION_EVENT_MISSING",
            )

        if event_type == "evidence.registered":
            if not isinstance(payload.get("evidence"), dict):
                raise InvalidStateError(
                    "Evidence event payload is not an object.",
                    "EVENT_PAYLOAD_INVALID",
                    {"event_id": event["event_id"]},
                )
            evidence_count += 1
        elif event_type == "hypothesis.created":
            hypothesis = payload.get("hypothesis")
            if not isinstance(hypothesis, dict):
                raise InvalidStateError(
                    "Hypothesis event payload is not an object.",
                    "EVENT_PAYLOAD_INVALID",
                    {"event_id": event["event_id"]},
                )
            state["active_experiment"]["hypothesis_id"] = hypothesis.get(
                "hypothesis_id"
            )
            state["active_experiment"]["hypothesis_revision"] = hypothesis.get(
                "revision"
            )
            state["active_experiment"]["hypothesis_approval"] = hypothesis.get(
                "approval"
            )
        elif event_type == "playtest.protocol.created":
            if not isinstance(payload.get("protocol"), dict):
                raise InvalidStateError(
                    "The event payload is not an object.",
                    "EVENT_PAYLOAD_INVALID",
                    {"event_id": event["event_id"]},
                )
        elif event_type == "decision.recorded":
            decision = payload.get("decision")
            transition = payload.get("transition")
            if not isinstance(decision, dict) or not isinstance(transition, dict):
                raise InvalidStateError(
                    "Decision event payload is incomplete.",
                    "EVENT_PAYLOAD_INVALID",
                    {"event_id": event["event_id"]},
                )
            if transition.get("from") != state["stage"] or not isinstance(
                transition.get("to"), str
            ):
                raise InvalidStateError(
                    "Decision transition does not match the projected stage.",
                    "TRANSITION_SOURCE_MISMATCH",
                    {"event_id": event["event_id"]},
                )
            if "hypothesis" in payload:
                hypothesis = payload["hypothesis"]
                if not isinstance(hypothesis, dict):
                    raise InvalidStateError(
                        "Decision hypothesis payload is not an object.",
                        "EVENT_PAYLOAD_INVALID",
                        {"event_id": event["event_id"]},
                    )
                state["active_experiment"]["hypothesis_id"] = hypothesis.get(
                    "hypothesis_id"
                )
                state["active_experiment"]["hypothesis_revision"] = hypothesis.get(
                    "revision"
                )
                state["active_experiment"]["hypothesis_approval"] = hypothesis.get(
                    "approval"
                )
            state["stage"] = transition["to"]
        elif event_type == "stage.transitioned":
            expected_from = payload.get("from")
            if not isinstance(expected_from, str) or not isinstance(
                payload.get("to"), str
            ):
                raise InvalidStateError(
                    "Stage transition payload is invalid.",
                    "EVENT_PAYLOAD_INVALID",
                    {"event_id": event["event_id"]},
                )
            if state["stage"] != expected_from:
                raise InvalidStateError(
                    "A stage transition does not match the projected stage.",
                    "TRANSITION_SOURCE_MISMATCH",
                    {
                        "expected": state["stage"],
                        "event_from": expected_from,
                        "event_id": event["event_id"],
                    },
                )
            state["stage"] = payload["to"]

        state["revision"] = event["revision"]
        state["evidence_count"] = evidence_count
        state["last_event_id"] = event["event_id"]
        state["last_event_hash"] = event["event_hash"]

    if state is None:
        raise InvalidStateError(
            "The event log is empty.",
            "INITIALIZATION_EVENT_MISSING",
        )
    return state
