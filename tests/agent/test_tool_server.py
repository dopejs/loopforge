"""Which `loopforge` the daemon is told to spawn as the tool server.

The agent registers this project's commands with Kura as an MCP server over
stdio, and the daemon starts that server as a subprocess. Resolving it from
PATH found a `loopforge` installed from the git remote months earlier, with no
`mcp` subcommand: argparse rejected the argument, the process exited 2 before
writing a frame, and the daemon reported `mcp transport is closed`. Nothing
named the binary. The agent had no tools and said so by narrating -- the user
saw a turn stop at "checking project state".
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from loopforge.agent.supervisor import KuraRuntimeSupervisor
from loopforge.project import LoopforgeProject
from loopforge.userstore import UserStore


def _frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return b"Content-Length: %d\r\n\r\n%s" % (len(body), body)


class ToolServerCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = UserStore(self.root / "home")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _supervisor(self) -> KuraRuntimeSupervisor:
        return KuraRuntimeSupervisor(
            LoopforgeProject(self.root / "project"),
            dope_binary="/bin/false",
            user_store=self.store,
        )

    def _decoy(self, name: str = "loopforge") -> Path:
        """A `loopforge` on PATH that is not this one.

        Written to behave the way the installed one did: it knows the commands
        of an older Loopforge and rejects `mcp`.
        """
        directory = self.root / "decoy-bin"
        directory.mkdir(exist_ok=True)
        script = directory / name
        script.write_text(
            "#!/bin/sh\n"
            'echo "loopforge: error: argument command: invalid choice: '
            "'mcp'\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return directory

    def test_registered_command_can_actually_serve_tools(self) -> None:
        """The whole point: spawn what would be registered, and speak to it.

        Asserting the shape of the resolution would have passed against the
        stale binary too -- it was a real path to a real executable named
        `loopforge`. The only check that discriminates is running it.
        """
        supervisor = self._supervisor()
        invocation = supervisor._loopforge_invocation()
        self.assertIsNotNone(invocation)
        command, prefix = invocation

        project = self.root / "project"
        project.mkdir(exist_ok=True)
        process = subprocess.run(
            [command, *prefix, "--project", str(project), "mcp"],
            input=_frame(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                }
            ),
            capture_output=True,
            timeout=60,
        )

        self.assertIn(
            b"Content-Length:",
            process.stdout,
            f"tool server wrote no frame; stderr={process.stderr!r}",
        )
        self.assertIn(b'"serverInfo"', process.stdout)

    def test_prefers_this_build_over_whatever_shares_the_name_on_path(self) -> None:
        # The bug exactly. A `loopforge` earlier on PATH must not win: the tool
        # server has to be the copy that ships with this agent, because it is
        # the one whose tools match the tier table the permission modes are
        # written against.
        decoy = self._decoy()
        original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{decoy}{os.pathsep}{original}"
        try:
            command, _ = self._supervisor()._loopforge_invocation()
        finally:
            os.environ["PATH"] = original

        self.assertNotEqual(Path(command).resolve(), (decoy / "loopforge").resolve())

    def test_refuses_a_fallback_that_does_not_speak_mcp(self) -> None:
        """Rather than registering it and learning at the handshake.

        With this build's own copy unavailable, PATH is all there is -- and a
        `loopforge` there that cannot serve tools must be rejected while
        something can still say which binary and why.
        """
        import loopforge.agent.supervisor as module

        decoy = self._decoy()
        original_path = os.environ.get("PATH", "")
        original_find = module.importlib.util.find_spec
        os.environ["PATH"] = str(decoy)
        module.importlib.util.find_spec = lambda name: (
            None if name == "loopforge.__main__" else original_find(name)
        )
        try:
            with self.assertLogs(module.LOGGER, level="WARNING") as logged:
                self.assertIsNone(self._supervisor()._loopforge_invocation())
        finally:
            os.environ["PATH"] = original_path
            module.importlib.util.find_spec = original_find

        self.assertIn("loopforge mcp", "\n".join(logged.output))

    def test_accepts_a_fallback_that_does_speak_mcp(self) -> None:
        # Or the probe would reject everything and the fallback would be dead
        # code that looks like a safety check.
        import loopforge.agent.supervisor as module

        directory = self.root / "good-bin"
        directory.mkdir()
        shim = directory / "loopforge"
        shim.write_text(
            "#!/bin/sh\nexec %s -m loopforge \"$@\"\n" % module.sys.executable,
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

        original_path = os.environ.get("PATH", "")
        original_find = module.importlib.util.find_spec
        os.environ["PATH"] = str(directory)
        module.importlib.util.find_spec = lambda name: (
            None if name == "loopforge.__main__" else original_find(name)
        )
        try:
            invocation = self._supervisor()._loopforge_invocation()
        finally:
            os.environ["PATH"] = original_path
            module.importlib.util.find_spec = original_find

        self.assertIsNotNone(invocation)
        self.assertEqual(Path(invocation[0]).resolve(), shim.resolve())

    def test_the_frozen_dispatch_flag_is_the_one_the_agent_answers_to(self) -> None:
        # Two files, one protocol, and a mismatch is invisible until a packaged
        # build starts a tool server that runs the daemon supervisor instead.
        from loopforge.agent.supervisor import CLI_DISPATCH_FLAG

        source = (
            Path(__file__).resolve().parents[2]
            / "apps"
            / "agent"
            / "loopforge_agent"
            / "__main__.py"
        ).read_text(encoding="utf-8")

        self.assertIn(f'CLI_DISPATCH_FLAG = "{CLI_DISPATCH_FLAG}"', source)


if __name__ == "__main__":
    unittest.main()
