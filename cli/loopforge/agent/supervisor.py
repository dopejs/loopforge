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
from ..userstore import UserStore
from ..project import LoopforgeProject
from .contracts import build_project_context
from .kura_client import KuraAgentError, KuraClient

RUNTIME_SCHEMA = "kura-runtime-v1"

#: Starting the daemon is meant to return immediately -- it forks and exits.
#: A binary that does not is either a different program under the same name or
#: is wedged, and either way waiting forever turns a diagnosable failure into a
#: hang. This bound was added after an obsolete `dope` on PATH, from before the
#: rename, blocked a start for seven minutes with no output.
DAEMON_COMMAND_TIMEOUT_SECONDS = 60.0

#: A drafted hypothesis is eleven sections; the default half minute is short.
#: Applied to every provider rather than to one named slot.
#:
#: These were keyed to `KURA_LLM_OPENAI_COMPATIBLE_*`, which stopped reaching
#: anything once providers were registered under their own ids -- leaving a
#: drafting request, which is eleven sections, on the daemon's thirty-second
#: default.
PROVIDER_TIMEOUTS = {
    "KURA_LLM_DEFAULT_TIMEOUT_MS": "180000",
}


class KuraRuntimeSupervisor:
    def __init__(
        self,
        project: LoopforgeProject,
        dope_binary: str | None = None,
        user_store: UserStore | None = None,
    ) -> None:
        self.project = project
        # User-level, so one configuration serves every project on this machine.
        self.user_store = user_store or UserStore()
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
        # Providers are passed as accounts, each under its own id. The single
        # `KURA_LLM_OPENAI_COMPATIBLE_*` slot is not used for them: it produces
        # a second profile with a fixed id and title, which collided with the
        # registered one and won -- so an endpoint the user had named came back
        # as "OpenAI-Compatible" with no models.
        environment.update(self._account_environment())
        try:
            completed = subprocess.run(
                [binary, "daemon", "start"],
                env=environment,
                cwd=self.project.root,
                text=True,
                capture_output=True,
                check=False,
                timeout=DAEMON_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            # Naming the binary is the point: the usual cause is the wrong one
            # being found on PATH, and a message without it sends the reader
            # looking at the daemon instead of at which daemon.
            raise LoopforgeError(
                "The Kura daemon did not finish starting.",
                "KURA_START_TIMEOUT",
                1,
                {
                    "binary": binary,
                    "timeout_seconds": DAEMON_COMMAND_TIMEOUT_SECONDS,
                    "bind_addr": bind_addr,
                },
            ) from exc
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
            try:
                subprocess.run(
                    [binary, "daemon", "stop"],
                    env=environment,
                    cwd=self.project.root,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=DAEMON_COMMAND_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                # Best-effort cleanup: the unhealthy start below is the error
                # worth reporting, and replacing it with a stop timeout would
                # hide why the daemon was being stopped.
                pass
            self.metadata_path.unlink(missing_ok=True)
            raise LoopforgeError(
                "Kura started but did not become healthy.", "KURA_NOT_READY", 1, result
            )
        return result

    def _account_environment(self) -> dict[str, str]:
        """Every signed-in subscription, as providers Kura can dispatch at.

        One entry per account rather than a slot per vendor: a person holds
        whichever subscriptions they signed into, and most of those vendors
        speak the OpenAI-compatible shape, so the set costs nothing beyond the
        two wires Anthropic and Codex each need.

        Accounts whose dispatch endpoint is not established are left out. They
        can still be signed in and read for usage; they are simply not somewhere
        a request is routed at a guess.

        The token here is only what the daemon starts with -- it is replaced in
        place as it is refreshed, because an access token lasts about an hour.
        """
        try:
            from ..oauth.registry import provider as oauth_provider

            grants = self.user_store.oauth_grants()
        except Exception:
            # A store this build cannot read must not stop a daemon that would
            # otherwise run on a configured endpoint.
            return {}

        accounts: list[dict[str, str]] = []
        # Everything the user configured, whatever it was added from. A
        # provider registered while the daemon runs lives only in its memory,
        # so without this a restart loses it and the endpoint reappears under
        # the built-in slot's name -- which is what made an Anthropic endpoint
        # come back called `openai_compatible` with no models.
        try:
            configured = self.user_store.providers()
        except Exception:
            configured = []
        for record in configured:
            base_url = str(record.get("base_url") or "").strip()
            model = str(record.get("model") or "").strip()
            if not base_url or not model:
                continue
            accounts.append(
                {
                    "id": str(record.get("provider_id") or ""),
                    "title": str(record.get("display_name") or record.get("provider_id") or ""),
                    "protocol": str(record.get("protocol") or "openai_compatible"),
                    "baseURL": base_url,
                    "model": model,
                    "accessToken": str(record.get("api_key") or ""),
                }
            )

        known = {account["id"] for account in accounts}
        for row in grants:
            try:
                target = oauth_provider(str(row.get("provider_id") or ""))
            except KeyError:
                continue
            if not target.api_base_url:
                continue
            token = str(row.get("access_token") or "")
            if not token or target.id in known:
                continue
            accounts.append(
                {
                    "id": target.id,
                    "title": target.name,
                    "protocol": target.protocol,
                    "baseURL": target.api_base_url,
                    "model": target.default_model,
                    "accessToken": token,
                }
            )
        if not accounts:
            return {}
        return {
            "KURA_LLM_ACCOUNTS": json.dumps(accounts),
            # Something has to answer when a request names no provider, and
            # the first one configured is the only defensible choice: the
            # daemon ships none of its own to fall back to.
            "KURA_LLM_DEFAULT_PROVIDER": accounts[0]["id"],
            **PROVIDER_TIMEOUTS,
        }

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
        try:
            completed = subprocess.run(
                [binary, "daemon", "stop"],
                env=environment,
                cwd=self.project.root,
                text=True,
                capture_output=True,
                check=False,
                timeout=DAEMON_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise LoopforgeError(
                "The Kura daemon did not finish stopping.",
                "KURA_STOP_TIMEOUT",
                1,
                {"binary": binary, "timeout_seconds": DAEMON_COMMAND_TIMEOUT_SECONDS},
            ) from exc
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
