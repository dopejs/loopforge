"""An isolated, real Kura daemon for integration tests.

Unit tests stub `KuraClient`, which is fast but cannot catch the failures that
actually bite: a client rejecting a URL shape, an endpoint requiring a bearer
token, a response field that is named differently than assumed. Those only
surface against a running daemon, so this fixture makes that cheap enough to do
in the normal test run.

Each instance gets its own data directory and an ephemeral port, so tests never
collide with each other or with a developer's `~/.kura*` daemons.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from loopforge.agent.kura_client import KuraAgentError, KuraClient

_STARTUP_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.2


def kura_binary() -> str | None:
    """Locate a Kura binary: explicit override, submodule build, then PATH."""
    override = os.environ.get("LOOPFORGE_KURA_BIN")
    if override and Path(override).is_file():
        return override
    repository_root = Path(__file__).resolve().parents[2]
    built = (
        repository_root
        / "apps"
        / "workbench"
        / "vendor"
        / "kura"
        / "crates"
        / "target"
        / "release"
        / "kura"
    )
    if built.is_file():
        return str(built)
    return shutil.which("kura")


#: Integration tests are skipped rather than failed when no daemon binary is
#: available, so CI (which does not build the sidecar) stays green while a
#: developer with a build gets the coverage.
requires_kura = unittest.skipUnless(
    kura_binary() is not None,
    "needs a Kura binary: run `pnpm build:kura` or set LOOPFORGE_KURA_BIN",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class KuraDaemon:
    """A running daemon plus an authenticated client for it."""

    def __init__(self) -> None:
        self.binary = kura_binary()
        if self.binary is None:
            raise unittest.SkipTest("no Kura binary available")
        self.data_dir = Path(tempfile.mkdtemp(prefix="loopforge-kura-test-"))
        self.bind_addr = f"127.0.0.1:{_free_port()}"
        self.base_url = f"http://{self.bind_addr}"
        self.token: str | None = None
        self._environment = {
            **os.environ,
            "KURA_ENV": "embedded",
            "KURA_DATA_DIR": str(self.data_dir),
            "KURA_BIND_ADDR": self.bind_addr,
        }

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> KuraDaemon:
        completed = subprocess.run(
            [self.binary, "daemon", "start"],
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.stop()
            raise RuntimeError(f"Kura daemon failed to start: {completed.stderr[-2000:]}")
        self._await_health()
        self.token = self._pair()
        return self

    def stop(self) -> None:
        if self.binary:
            subprocess.run(
                [self.binary, "daemon", "stop"],
                env=self._environment,
                capture_output=True,
                check=False,
            )
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def __enter__(self) -> KuraDaemon:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()

    # -- access -------------------------------------------------------------

    def client(self, timeout: float = 15.0) -> KuraClient:
        return KuraClient(self.base_url, timeout=timeout, token=self.token)

    def anonymous_client(self, timeout: float = 15.0) -> KuraClient:
        """A client without the bearer token, for asserting that /v1 is closed."""
        return KuraClient(self.base_url, timeout=timeout)

    # -- internals ----------------------------------------------------------

    def _await_health(self) -> None:
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        client = KuraClient(self.base_url, timeout=2.0)
        while time.monotonic() < deadline:
            try:
                if client.get("/healthz").get("ok"):
                    return
            except KuraAgentError:
                pass
            time.sleep(_POLL_INTERVAL_SECONDS)
        raise RuntimeError(f"Kura daemon did not become healthy at {self.base_url}")

    def _pair(self) -> str:
        client = KuraClient(self.base_url, timeout=15.0)
        started: dict[str, Any] = client.post(
            "/v1/auth/pairings/start",
            {"mode": "local", "label": "loopforge-tests", "ttlSeconds": 300},
        )
        pairing_id = started["pairing"]["pairingId"]
        completed = client.post(
            f"/v1/auth/pairings/{pairing_id}/complete", {"code": started["pairingCode"]}
        )
        return str(completed["accessToken"])
