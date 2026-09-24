"""The Agent, and -- under one flag -- the CLI it needs to spawn.

A packaged build ships a single binary. The agent registers Loopforge's own
commands with the daemon as an MCP tool server, and the daemon spawns that
server as a subprocess, so the CLI has to be reachable as a process. Resolving
it from PATH found a `loopforge` installed from the git remote months earlier,
with no `mcp` subcommand: it exited before the handshake and the only thing
reported was `mcp transport is closed`.

So the binary answers to both. There is no interpreter to hand `-m loopforge`
to in a frozen build, and shipping a second executable would only move the
question of which copy is which -- one file cannot disagree with itself.

Kept as an argument rather than a second entry point name so it cannot be
reached by accident: `sys.argv[0]` is whatever the daemon was told to run, and
dispatching on it would make a rename change what the program does.
"""

import sys

#: Must match `loopforge.agent.supervisor.CLI_DISPATCH_FLAG`.
CLI_DISPATCH_FLAG = "--loopforge-cli"


def _run() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == CLI_DISPATCH_FLAG:
        from loopforge.cli import main as cli_main

        # Dropped so the CLI sees its own arguments: it parses `--project`
        # before a subcommand and would reject the flag that got it here.
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        return cli_main()

    from loopforge_agent.server import main

    return main()


raise SystemExit(_run())
