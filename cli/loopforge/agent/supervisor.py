from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

from ..errors import InvalidStateError, LoopforgeError, ToolUnavailableError
from ..jsonutil import atomic_write_json
from ..project import LoopforgeProject
from .contracts import build_project_context
from .kura_client import KuraAgentError, KuraClient

RUNTIME_SCHEMA = "kura-runtime-v1"


class AgentSupervisor:
    def __init__(
        self, project: LoopforgeProject, dope_binary: str | None = None
    ) -> None:
        self.project = project
        self.root = project.root / ".loopforge" / "agent"
        self.metadata_path = self.root / "runtime.json"
        self.context_path = self.root / "context.json"
        self.dope_binary = (
            dope_binary
            or os.environ.get("LOOPFORGE_KURA_BIN")
            or os.environ.get("LOOPFORGE_DOPE_BIN")
            or shutil.which("dope-cli")
            or shutil.which("dope")
        )

    def _metadata(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise InvalidStateError(
                "Kura runtime metadata is not valid JSON.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            ) from exc
        if not isinstance(value, dict):
            raise InvalidStateError(
                "Kura runtime metadata must be a JSON object.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            )
        self._validate_metadata(value)
        return value

    def _validate_metadata(self, metadata: dict[str, Any]) -> None:
        bind_addr = metadata.get("bind_addr")
        data_dir = metadata.get("data_dir")
        if metadata.get("schema_version") != RUNTIME_SCHEMA:
            raise InvalidStateError(
                "Kura runtime metadata has an unsupported schema version.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            )
        if not isinstance(bind_addr, str) or not isinstance(data_dir, str):
            raise InvalidStateError(
                "Kura runtime metadata is missing required fields.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            )
        try:
            parsed = urllib.parse.urlsplit(f"//{bind_addr}")
            address = ipaddress.ip_address(parsed.hostname or "")
            port = parsed.port
        except ValueError as exc:
            raise InvalidStateError(
                "Kura runtime metadata has an invalid bind address.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            ) from exc
        if (
            not address.is_loopback
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise InvalidStateError(
                "Kura runtime metadata must use a loopback address and explicit port.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            )
        expected_data_dir = (self.root / "data").resolve()
        if Path(data_dir).resolve() != expected_data_dir:
            raise InvalidStateError(
                "Kura runtime metadata references an unexpected data directory.",
                "KURA_RUNTIME_INVALID",
                {"path": str(self.metadata_path)},
            )

    def _base_url(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None
        bind = str(metadata.get("bind_addr", ""))
        return f"http://{bind}" if bind else None

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _require_binary(self) -> str:
        if not self.dope_binary:
            raise ToolUnavailableError(
                "The Kura daemon binary was not found on PATH.",
                {
                    "expected": ["dope-cli", "dope"],
                    "remediation": "Build or install Kura, then retry.",
                },
            )
        return self.dope_binary

    def start(self, port: int | None = None) -> dict[str, Any]:
        binary = self._require_binary()
        self.root.mkdir(parents=True, exist_ok=True)
        existing = self.status()
        if existing["running"]:
            return existing
        bind_addr = f"127.0.0.1:{port or self._free_port()}"
        data_dir = self.root / "data"
        environment = os.environ.copy()
        environment.update(
            {
                "DOPE_ENV": "test",
                "DOPE_DATA_DIR": str(data_dir),
                "DOPE_BIND_ADDR": bind_addr,
            }
        )
        completed = subprocess.run(
            [binary, "daemon", "start"],
            env=environment,
            cwd=self.project.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise LoopforgeError(
                "Kura daemon failed to start.",
                "DOPE_AGENT_START_FAILED",
                1,
                {
                    "stderr": completed.stderr[-2000:],
                    "stdout": completed.stdout[-2000:],
                    "bind_addr": bind_addr,
                },
            )
        metadata = {
            "schema_version": RUNTIME_SCHEMA,
            "bind_addr": bind_addr,
            "data_dir": str(data_dir),
            "started_at": time.time(),
        }
        atomic_write_json(self.metadata_path, metadata)
        result = self.status()
        if not result["healthy"]:
            subprocess.run(
                [binary, "daemon", "stop"],
                env=environment,
                cwd=self.project.root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.metadata_path.unlink(missing_ok=True)
            raise LoopforgeError(
                "Kura started but did not become healthy.", "KURA_NOT_READY", 1, result
            )
        return result

    def stop(self) -> dict[str, Any]:
        metadata = self._metadata()
        if not metadata:
            return {"running": False, "healthy": False, "reason": "no_runtime_metadata"}
        binary = self._require_binary()
        environment = os.environ.copy()
        environment.update(
            {
                "DOPE_ENV": "test",
                "DOPE_DATA_DIR": str(metadata["data_dir"]),
                "DOPE_BIND_ADDR": str(metadata["bind_addr"]),
            }
        )
        completed = subprocess.run(
            [binary, "daemon", "stop"],
            env=environment,
            cwd=self.project.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise LoopforgeError(
                "Kura daemon failed to stop.",
                "KURA_STOP_FAILED",
                1,
                {"stderr": completed.stderr[-2000:]},
            )
        self.metadata_path.unlink(missing_ok=True)
        return {"running": False, "healthy": False, "stopped": True}

    def status(self) -> dict[str, Any]:
        metadata = self._metadata()
        base_url = self._base_url(metadata)
        result: dict[str, Any] = {
            "running": False,
            "healthy": False,
            "managed": metadata is not None,
            "base_url": base_url,
        }
        if not base_url:
            return result
        try:
            health = KuraClient(base_url).get("/healthz")
            result.update(
                {
                    "running": True,
                    "healthy": bool(health.get("ok")),
                    "health": health,
                    "version": KuraClient(base_url).get("/version"),
                }
            )
        except KuraAgentError as exc:
            result.update({"reason": str(exc), "error_code": exc.code})
        return result

    def doctor(self) -> dict[str, Any]:
        status = self.status()
        checks = [
            {
                "code": "DOPE_BINARY",
                "status": "passed" if self.dope_binary else "failed",
                "path": self.dope_binary,
            }
        ]
        checks.append(
            {
                "code": "DAEMON_HEALTH",
                "status": "passed" if status["healthy"] else "warning",
                "details": status,
            }
        )
        return {
            "healthy": bool(self.dope_binary and status["healthy"]),
            "checks": checks,
            "status": status,
        }

    def context(self) -> dict[str, Any]:
        return build_project_context(self.project)

    def sync_context(self) -> dict[str, Any]:
        context = self.context()
        atomic_write_json(self.context_path, context)
        return {
            "context": context,
            "context_path": str(self.context_path),
            "synchronized": True,
        }
