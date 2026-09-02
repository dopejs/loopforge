"""Loopforge's deterministic commands, published as MCP tools.

An agent that can only describe `loopforge status` is not an agent. This is the
server that lets one run it: a stdio MCP server speaking `Content-Length`-framed
JSON-RPC, publishing the read-only commands as tools and answering them from the
same code path the CLI uses.

Two kinds of tool, and the difference is who decides.

Reading project state is something the agent may simply do. Changing it is not:
Loopforge's whole claim is that a stage transition cites evidence and records a
human approver, and a tool that let a model advance a stage on its own would
make that claim false while leaving the record looking correct.

So the mutating commands are published under `approval_required` and the
read-only ones under `allow`. The runtime raises an approval naming the tool and
its arguments, waits for a person, and runs the call only if they say yes. That
is only safe because the person can see what they are approving -- "may the
agent run `advance`" has no answer without knowing what it would advance to.

The split is declared here, on the tool, rather than left to whoever writes the
exposure rules: a rule can be misconfigured, and a tool that says what it is
cannot be turned into the other kind by getting one wrong.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .project import LoopforgeProject

#: What this server answers to. Kura's transport sends this on connect.
PROTOCOL_VERSION = "2024-11-05"

#: A tool's answer is JSON the model reads. Bounded because a project with a
#: long history can produce a large one, and a tool result becomes part of every
#: later round's prompt.
MAX_RESULT_CHARS = 24000


class Tool:
    """One published command."""

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict[str, Any],
        run: Callable[[LoopforgeProject, dict[str, Any]], Any],
        *,
        mutates: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self.run = run
        #: Whether running this changes project state. Decides which exposure
        #: rule it is published under, and it is a property of the command
        #: rather than of the configuration.
        self.mutates = mutates

    def declaration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema,
        }


#: An empty object rather than an absent schema: a tool that takes nothing still
#: has to say so, or a provider is left to guess the shape of the arguments.
NO_ARGUMENTS: dict[str, Any] = {"type": "object", "properties": {}}


def _status(project: LoopforgeProject, _arguments: dict[str, Any]) -> Any:
    return project.status()


def _inspect(project: LoopforgeProject, _arguments: dict[str, Any]) -> Any:
    return project.inspect()


def _history(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    events = project.history()["events"]
    limit = arguments.get("limit")
    if isinstance(limit, int) and limit > 0:
        # Newest last, so the tail is what a caller asking for "the last few"
        # means.
        events = events[-limit:]
    return {"events": events}


def _validate(project: LoopforgeProject, _arguments: dict[str, Any]) -> Any:
    return project.validate()


def _revision(project: LoopforgeProject, arguments: dict[str, Any]) -> int | None:
    """The revision a mutation expects to be applied to.

    Optional, and absent means "whatever is current". A model that read the
    state a moment ago can pass what it saw, and the core refuses the write if
    something else moved in between -- which is the only protection against two
    writers there is.
    """
    expected = arguments.get("expected_revision")
    return expected if isinstance(expected, int) and expected >= 0 else None


def _run_engine(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    operation = str(arguments.get("operation") or "").strip()
    if operation not in ("build", "test"):
        raise ValueError("operation must be 'build' or 'test'")
    return project.run_engine(operation, _revision(project, arguments))


def _gate(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    return project.gate_check(str(arguments.get("target_stage") or "").strip())


def _advance(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    return project.advance(
        str(arguments.get("target_stage") or "").strip(),
        _revision(project, arguments),
        str(arguments.get("reason") or "") or None,
    )


def _capture(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    return project.register_capture(str(arguments.get("path") or "").strip())


#: A stage name, spelled out. A model that invents one should be refused by the
#: schema rather than by the core after a round trip.
STAGE = {
    "type": "string",
    "enum": [
        "DISCOVERY",
        "PROTOTYPING",
        "PLAYTEST_REQUIRED",
        "PROTOTYPE_DECISION",
        "VERTICAL_SLICE",
        "KILLED",
    ],
}

#: Offered on every mutation. The core refuses a write whose expected revision
#: has moved, which is what stops two writers from overwriting each other.
EXPECTED_REVISION = {
    "type": "integer",
    "minimum": 0,
    "description": "The revision this change expects. Omit to apply to whatever is current.",
}


TOOLS: tuple[Tool, ...] = (
    Tool(
        "loopforge_status",
        "The project's current stage, revision, quality claims and the actions "
        "allowed next. Read this before proposing any work.",
        NO_ARGUMENTS,
        _status,
    ),
    Tool(
        "loopforge_inspect",
        "What is in the project directory: the detected engine, whether "
        "Loopforge is initialized, and which tools are on PATH.",
        NO_ARGUMENTS,
        _inspect,
    ),
    Tool(
        "loopforge_history",
        "Committed project events, oldest first. Use this to explain how the "
        "project reached its current stage.",
        {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Return only the most recent N events.",
                    "minimum": 1,
                }
            },
        },
        _history,
    ),
    Tool(
        "loopforge_validate",
        "Check project state and event history for integrity problems, and "
        "report the diagnostics without repairing anything.",
        NO_ARGUMENTS,
        _validate,
    ),
    # -- changing it ------------------------------------------------------
    #
    # Each of these is published under `approval_required`: the runtime asks a
    # person, naming the tool and the arguments, and runs the call only if they
    # say yes.
    Tool(
        "loopforge_gate",
        "Check whether the project satisfies the gate into a stage, without "
        "moving it. Reports which requirements are unmet.",
        {
            "type": "object",
            "properties": {"target_stage": STAGE},
            "required": ["target_stage"],
        },
        _gate,
        mutates=True,
    ),
    Tool(
        "loopforge_run",
        "Run a build or test through the engine adapter and record what it "
        "produced as evidence.",
        {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["build", "test"]},
                "expected_revision": EXPECTED_REVISION,
            },
            "required": ["operation"],
        },
        _run_engine,
        mutates=True,
    ),
    Tool(
        "loopforge_capture",
        "Register a runtime capture -- a screenshot or recording already on "
        "disk -- as visual evidence.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the capture."}
            },
            "required": ["path"],
        },
        _capture,
        mutates=True,
    ),
    Tool(
        "loopforge_advance",
        "Move the project into a stage. Refused unless the gate passes, and "
        "the transition records who approved it.",
        {
            "type": "object",
            "properties": {
                "target_stage": STAGE,
                "reason": {"type": "string"},
                "expected_revision": EXPECTED_REVISION,
            },
            "required": ["target_stage"],
        },
        _advance,
        mutates=True,
    ),
)


def _tool(name: str) -> Tool | None:
    return next((tool for tool in TOOLS if tool.name == name), None)


def read_frame(stream: BinaryIO) -> bytes | None:
    """Read one `Content-Length` framed message, or None at end of input.

    Headers are read line by line rather than by scanning for a blank line in a
    buffer: the stream is a pipe, and reading past the frame would consume the
    beginning of the next one.
    """
    length = 0
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if line.lower().startswith(b"content-length:"):
            try:
                length = int(line.split(b":", 1)[1].strip())
            except ValueError:
                return None
    if length <= 0:
        return b""
    return stream.read(length)


def write_frame(stream: BinaryIO, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def _text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _bounded(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return text
    # Truncated visibly. A silently shortened result would be read as the whole
    # answer, and a model would reason from a project state that is missing its
    # tail without knowing it.
    return text[:MAX_RESULT_CHARS] + f'… [truncated at {MAX_RESULT_CHARS} characters]'


def respond(request: dict[str, Any], project_root: Path) -> dict[str, Any] | None:
    """Answer one request. Returns None for a notification, which has no id."""
    request_id = request.get("id")
    if request_id is None or (isinstance(request_id, str) and not request_id.strip()):
        return None
    method = str(request.get("method") or "")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "loopforge", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": [tool.declaration() for tool in TOOLS]},
        }

    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        tool = _tool(name)
        if tool is None:
            # An error the model can act on, not a protocol failure: it named a
            # tool that does not exist and can name a real one next round.
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {**_text_result(f"no such tool: {name}"), "isError": True},
            }
        try:
            payload = tool.run(LoopforgeProject(project_root), arguments)
        except Exception as error:  # noqa: BLE001 - reported, never raised
            # A command that refuses is an answer. An uninitialized project is
            # the ordinary case, and the model needs to be told which it is
            # rather than seeing the server die.
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {**_text_result(f"{type(error).__name__}: {error}"), "isError": True},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": _text_result(_bounded(payload))}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def serve(project_root: Path, stdin: BinaryIO, stdout: BinaryIO) -> None:
    """Answer requests until the input closes."""
    while True:
        payload = read_frame(stdin)
        if payload is None:
            return
        if not payload:
            continue
        try:
            request = json.loads(payload)
        except json.JSONDecodeError:
            # Unframeable input is not something to answer: there is no id to
            # answer it under.
            continue
        if not isinstance(request, dict):
            continue
        response = respond(request, project_root)
        if response is not None:
            write_frame(stdout, response)


def main(project_root: Path) -> int:
    serve(project_root, sys.stdin.buffer, sys.stdout.buffer)
    return 0
