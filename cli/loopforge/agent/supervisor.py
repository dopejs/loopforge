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


class KuraRuntimeSupervisor:
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
            or shutil.which("kura")
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

    @staticmethod
    def _pair(base_url: str) -> str | None:
        """Exchange a local pairing for a bearer token.

        Kura protects every `/v1` route. The pairing start and complete routes
        are deliberately unauthenticated, and `local` mode returns the code in
        the start response, so a supervisor that already owns the daemon
        process can complete the exchange without a human step. Reaching the
        loopback port is itself the proof of local access.

        Returns `None` rather than raising: an older runtime without pairing
        should still start, and the caller surfaces the resulting auth failure
        with more context than a start-time crash would.
        """
        client = KuraClient(base_url, timeout=10.0)
        try:
            started = client.post(
                "/v1/auth/pairings/start",
                {"mode": "local", "label": "loopforge-agent", "ttlSeconds": 300},
            )
            pairing = started.get("pairing")
            code = started.get("pairingCode")
            if not isinstance(pairing, dict) or not isinstance(code, str):
                return None
            pairing_id = pairing.get("pairingId")
            if not isinstance(pairing_id, str) or not pairing_id:
                return None
            completed = client.post(
                f"/v1/auth/pairings/{urllib.parse.quote(pairing_id, safe='')}/complete",
                {"code": code},
            )
        except KuraAgentError:
            return None
        token = completed.get("accessToken")
        return token if isinstance(token, str) and token else None

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
                    "expected": ["kura", "dope-cli"],
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
                # Loopforge supervises one Kura daemon per project and supplies
                # the data dir and port itself. `embedded` is Kura's supported
                # shape for that; it keeps the test isolation (per-workspace
                # managed-provider home, no hosted billing quotas) without
                # claiming to be a developer test daemon.
                "KURA_ENV": "embedded",
                "KURA_DATA_DIR": str(data_dir),
                "KURA_BIND_ADDR": bind_addr,
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
        token = self._pair(f"http://{bind_addr}")
        if token:
            metadata["token"] = token
        # The metadata carries a bearer token for the daemon. Atomic writes
        # already land at 0600 because the temporary file is created with
        # mkstemp semantics; stating it here keeps that guarantee from
        # depending on an implementation detail elsewhere.
        atomic_write_json(self.metadata_path, metadata, mode=0o600)
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
                # Loopforge supervises one Kura daemon per project and supplies
                # the data dir and port itself. `embedded` is Kura's supported
                # shape for that; it keeps the test isolation (per-workspace
                # managed-provider home, no hosted billing quotas) without
                # claiming to be a developer test daemon.
                "KURA_ENV": "embedded",
                "KURA_DATA_DIR": str(metadata["data_dir"]),
                "KURA_BIND_ADDR": str(metadata["bind_addr"]),
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
        token = metadata.get("token") if isinstance(metadata, dict) else None
        result: dict[str, Any] = {
            "running": False,
            "healthy": False,
            "managed": metadata is not None,
            "base_url": base_url,
            # Callers need this to reach any /v1 route; /healthz is the only
            # unauthenticated one.
            "token": token if isinstance(token, str) and token else None,
        }
        if not base_url:
            return result
        try:
            client = KuraClient(base_url, token=result["token"])
            health = client.get("/healthz")
            result.update(
                {
                    "running": True,
                    "healthy": bool(health.get("ok")),
                    "health": health,
                    "version": client.get("/version"),
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


# Backward-compatible import for the alpha CLI surface. New application code
# should use KuraRuntimeSupervisor and keep LoopforgeAgent as the domain Agent.
AgentSupervisor = KuraRuntimeSupervisor
