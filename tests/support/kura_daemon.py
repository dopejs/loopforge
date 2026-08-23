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

#: A real model provider, supplied by the developer running the tests.
#:
#: The built-in `echo` provider proves the pipeline carries a request and
#: parses a reply, but it cannot answer in a requested format, so it says
#: nothing about whether a draft is usable. These variables opt a run into
#: asking a real model. The key is read from the environment and never written
#: to disk: Kura takes it as an override, so no config file holds it.
LIVE_PROVIDER_VARIABLES = (
    "LOOPFORGE_TEST_LLM_BASE_URL",
    "LOOPFORGE_TEST_LLM_API_KEY",
    "LOOPFORGE_TEST_LLM_MODEL",
)
_POLL_INTERVAL_SECONDS = 0.2


def kura_binary() -> str | None:
    """Locate a Kura binary: explicit override, submodule build, then PATH."""
    override = os.environ.get("LOOPFORGE_KURA_BIN")
    if override and Path(override).is_file():
        return override
    repository_root = Path(__file__).resolve().parents[2]
    workbench = repository_root / "apps" / "workbench"
    # The bundled copy first, because it is the one `pnpm build:kura` leaves
    # behind: that script deletes the Cargo target directory once it has
    # copied the binary out. Looking only in the target meant every
    # integration test skipped itself after a normal build, and a suite that
    # skips reads exactly like a suite that passes.
    for candidate in (
        workbench / "resources" / "kura",
        workbench / "vendor" / "kura" / "crates" / "target" / "release" / "kura",
    ):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("kura")


def stale_binary_reason() -> str | None:
    """Whether any submodule source is newer than the located binary.

    Found the hard way: a binary built before the commit that made the
    OpenAI-compatible provider dispatchable produced a dispatch failure that
    read exactly like a configuration problem. The tests were honest about what
    they saw and completely misleading about the cause, because nothing checked
    that the thing under test was the thing on disk.

    Compares against source modification times rather than the pinned commit
    date, because the normal order is build, test, then commit -- keying on the
    commit would call a correct binary stale for the minutes between.

    Returns None when the question cannot be answered -- no submodule, no
    binary, an explicit override -- since an unanswerable check must not block
    a run.
    """
    binary = kura_binary()
    if binary is None or os.environ.get("LOOPFORGE_KURA_BIN"):
        # An explicit override is the developer's own choice of binary.
        return None
    sources = (
        Path(__file__).resolve().parents[2]
        / "apps" / "workbench" / "vendor" / "kura" / "crates"
    )
    if not sources.is_dir():
        return None
    try:
        built = Path(binary).stat().st_mtime
        newer = subprocess.run(
            [
                "find", str(sources),
                "-name", "target", "-prune", "-o",
                "-newer", str(binary),
                "(", "-name", "*.rs", "-o", "-name", "*.toml", ")",
                "-print",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    del built
    changed = [line for line in newer.stdout.splitlines() if line.strip()]
    if not changed:
        return None
    example = Path(changed[0]).name
    return (
        f"{len(changed)} Kura source file(s) are newer than the built binary "
        f"(for example {example}); rebuild with `pnpm build:kura`"
    )


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


def live_provider() -> dict[str, str] | None:
    """The configured live provider, or None when the run is not opted in."""
    values = {name: os.environ.get(name, "").strip() for name in LIVE_PROVIDER_VARIABLES}
    return values if all(values.values()) else None


requires_live_provider = unittest.skipUnless(
    live_provider() is not None,
    "needs a live model: set "
    + ", ".join(LIVE_PROVIDER_VARIABLES),
)


class KuraDaemon:
    """A running daemon plus an authenticated client for it."""

    def __init__(self, live: bool = False) -> None:
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
            # Asked for by name, because the daemon no longer ships providers
            # nobody configured. Echo answers deterministically without
            # reaching anything, which is what lets these tests exercise
            # dispatch, routing and streaming with no real endpoint. A live
            # run replaces it below.
            "KURA_LLM_DEFAULT_PROVIDER": "echo",
        }
        if live:
            provider = live_provider()
            if provider is None:
                raise unittest.SkipTest("no live provider configured")
            # Passed as overrides so the credential stays in the environment
            # rather than being written into the daemon's config file.
            self._environment.update(
                {
                    "KURA_LLM_DEFAULT_PROVIDER": "openai_compatible",
                    "KURA_LLM_OPENAI_COMPATIBLE_BASE_URL": provider[
                        "LOOPFORGE_TEST_LLM_BASE_URL"
                    ],
                    "KURA_LLM_OPENAI_COMPATIBLE_API_KEY": provider[
                        "LOOPFORGE_TEST_LLM_API_KEY"
                    ],
                    "KURA_LLM_OPENAI_COMPATIBLE_MODEL": provider[
                        "LOOPFORGE_TEST_LLM_MODEL"
                    ],
                    # A real model drafting eleven sections needs longer than
                    # the default half minute.
                    "KURA_LLM_OPENAI_COMPATIBLE_TIMEOUT_MS": "180000",
                    "KURA_LLM_OPENAI_COMPATIBLE_STREAM_FIRST_CHUNK_TIMEOUT_MS": "120000",
                    "KURA_LLM_OPENAI_COMPATIBLE_STREAM_IDLE_TIMEOUT_MS": "120000",
                    "KURA_LLM_OPENAI_COMPATIBLE_STREAM_MAX_DURATION_MS": "300000",
                }
            )

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> KuraDaemon:
        stale = stale_binary_reason()
        if stale is not None:
            # Raised, not skipped: the binary exists and would answer, just
            # not as the pinned source says it should.
            raise RuntimeError(f"Kura daemon is out of date: {stale}")
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
