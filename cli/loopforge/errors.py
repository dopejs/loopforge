from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LoopforgeError(Exception):
    message: str
    diagnostic_code: str
    exit_code: int = 1
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class InvalidStateError(LoopforgeError):
    def __init__(
        self,
        message: str,
        diagnostic_code: str = "INVALID_PROJECT_STATE",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, diagnostic_code, 2, details or {})


class StateConflictError(LoopforgeError):
    def __init__(
        self,
        message: str,
        diagnostic_code: str = "STATE_CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, diagnostic_code, 5, details or {})


class GateBlockedError(LoopforgeError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "GATE_NOT_SATISFIED", 3, details or {})


class ToolUnavailableError(LoopforgeError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "REQUIRED_TOOL_UNAVAILABLE", 4, details or {})


class NotInitializedError(LoopforgeError):
    def __init__(self, project: str) -> None:
        super().__init__(
            "Loopforge is not initialized for this project.",
            "PROJECT_NOT_INITIALIZED",
            1,
            {"project": project, "remediation": "Run `loopforge init`."},
        )
