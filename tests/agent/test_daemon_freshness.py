"""Running the daemon that was built, and saying so when it will not run.

Three separate hours went into "Kura daemon failed to start" with empty stdout
and empty stderr. The cause each time was the same: on macOS, replacing a
binary at a path the kernel has already executed leaves it holding a signature
for the old inode, and it kills the new process outright. `codesign --verify`
calls the file valid throughout, so the only evidence was an exit status
nobody printed.

Compounding it: a Kura daemon forks and outlives the app that started it, so
restarting the app reconnects to the daemon a rebuild was meant to replace. The
fix was on disk and the bug was still running.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from loopforge.agent.supervisor import KuraRuntimeSupervisor, daemon_failure_detail
from loopforge.project import LoopforgeProject


class WhatAFailedCommandSays(unittest.TestCase):
    def test_names_the_kernel_when_it_killed_the_binary(self) -> None:
        # The whole point. An empty stderr and a bare "failed to start" is what
        # cost the hours; the exit status was there the whole time.
        detail = daemon_failure_detail(
            "/x/kura", SimpleNamespace(returncode=137, stderr="", stdout="")
        )

        self.assertEqual(detail["exit_code"], 137)
        self.assertIn("SIGKILL", detail["diagnosis"])
        self.assertIn("code signature", detail["diagnosis"])
        self.assertIn("codesign", detail["diagnosis"])

    def test_recognizes_the_signal_in_its_negative_form(self) -> None:
        # `subprocess` reports a signal as a negative number, and the shell
        # reports the same death as 137. Both are this.
        detail = daemon_failure_detail(
            "/x/kura", SimpleNamespace(returncode=-9, stderr="", stdout="")
        )

        self.assertIn("SIGKILL", detail["diagnosis"])

    def test_does_not_diagnose_an_ordinary_failure(self) -> None:
        # A binary that refused an argument said why. Attaching a signature
        # theory to it would send someone to re-sign a working file.
        detail = daemon_failure_detail(
            "/x/kura", SimpleNamespace(returncode=2, stderr="unknown flag", stdout="")
        )

        self.assertNotIn("diagnosis", detail)
        self.assertEqual(detail["stderr"], "unknown flag")

    def test_carries_the_exit_code_either_way(self) -> None:
        detail = daemon_failure_detail(
            "/x/kura", SimpleNamespace(returncode=1, stderr="", stdout="")
        )
        self.assertEqual(detail["exit_code"], 1)


class WhetherTheRunningDaemonIsCurrent(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.binary = self.root / "kura"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.supervisor = KuraRuntimeSupervisor(
            LoopforgeProject(self.root / "project"), dope_binary=str(self.binary)
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _started_at(self, when: float) -> None:
        self.supervisor.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        self.supervisor.metadata_path.write_text(
            json.dumps(
                {
                    "schema_version": "kura-runtime-v1",
                    "bind_addr": "127.0.0.1:1",
                    "data_dir": str(self.supervisor.root / "data"),
                    "started_at": when,
                }
            ),
            encoding="utf-8",
        )

    def test_a_daemon_older_than_the_binary_is_outdated(self) -> None:
        # The case that made a rebuild look like it had no effect.
        built = self.binary.stat().st_mtime
        self._started_at(built - 3600)

        self.assertIsNotNone(self.supervisor._outdated_reason(str(self.binary)))

    def test_a_daemon_newer_than_the_binary_is_left_alone(self) -> None:
        built = self.binary.stat().st_mtime
        self._started_at(built + 60)

        self.assertIsNone(self.supervisor._outdated_reason(str(self.binary)))

    def test_a_question_that_cannot_be_answered_does_not_restart_anything(self) -> None:
        # No metadata, no start time, no readable binary. An unanswerable check
        # must not take down a daemon that is working.
        self.assertIsNone(self.supervisor._outdated_reason(str(self.binary)))

        self._started_at(time.time())
        self.assertIsNone(self.supervisor._outdated_reason(str(self.root / "absent")))

        import json

        self.supervisor.metadata_path.write_text(
            json.dumps(
                {
                    "schema_version": "kura-runtime-v1",
                    "bind_addr": "127.0.0.1:1",
                    "data_dir": str(self.supervisor.root / "data"),
                }
            ),
            encoding="utf-8",
        )
        self.assertIsNone(self.supervisor._outdated_reason(str(self.binary)))

    def test_a_running_daemon_that_is_current_is_handed_back_as_is(self) -> None:
        built = self.binary.stat().st_mtime
        self._started_at(built + 60)
        self.supervisor.status = lambda: {"running": True, "healthy": True}  # type: ignore[method-assign]
        stopped: list[int] = []
        self.supervisor.stop = lambda: stopped.append(1)  # type: ignore[method-assign]

        answer = self.supervisor.start()

        self.assertTrue(answer["running"])
        self.assertEqual(stopped, [])

    def test_an_outdated_one_is_stopped_before_a_new_one_is_started(self) -> None:
        built = self.binary.stat().st_mtime
        self._started_at(built - 3600)
        self.supervisor.status = lambda: {"running": True, "healthy": True}  # type: ignore[method-assign]
        stopped: list[int] = []

        def stop():
            stopped.append(1)
            raise RuntimeError("stop reached")

        self.supervisor.stop = stop  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError):
            self.supervisor.start()

        self.assertEqual(stopped, [1])

    def test_a_daemon_that_will_not_stop_is_still_handed_back(self) -> None:
        # Worse than an old daemon is no daemon. The staleness travels with it
        # so a surface can say what it is looking at.
        from loopforge.errors import LoopforgeError

        built = self.binary.stat().st_mtime
        self._started_at(built - 3600)
        self.supervisor.status = lambda: {"running": True, "healthy": True}  # type: ignore[method-assign]

        def stop():
            raise LoopforgeError("no", "KURA_STOP_FAILED", 1, {})

        self.supervisor.stop = stop  # type: ignore[method-assign]

        answer = self.supervisor.start()

        self.assertTrue(answer["running"])
        self.assertIn("outdated", answer)


if __name__ == "__main__":
    unittest.main()
