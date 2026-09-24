"""Loopforge's deterministic commands, published as MCP tools.

An agent that can only describe `loopforge status` is not an agent. This is the
server that lets one run it: a stdio MCP server speaking `Content-Length`-framed
JSON-RPC, publishing the read-only commands as tools and answering them from the
same code path the CLI uses.

Three kinds of tool, because "does it write" is not the question a person
actually wants to answer.

  READ      Reports state and changes nothing. Nobody wants to be asked.
  EVIDENCE  Produces a record -- a build result, a capture. It is work, and
            work being done is not a claim about whether the work was good.
  CLAIM     Asserts something about the project: this stage is reached, this
            prototype is kept. Loopforge's whole value is that such a claim
            cites evidence and records a human approver.

The distinction matters because the middle tier is where a person spends their
day. Being asked before every build is how someone stops reading the questions,
and someone who stops reading them will approve a `CLAIM` without looking.

Which tier a command is in is declared here, on the command, rather than left to
whoever writes the exposure rules: a rule can be misconfigured, and a tool that
says what it is cannot be turned into another kind by getting one wrong.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

from .project import LoopforgeProject

#: What this server answers to. Kura's transport sends this on connect.
PROTOCOL_VERSION = "2024-11-05"

#: A tool's answer is JSON the model reads. Bounded because a project with a
#: long history can produce a large one, and a tool result becomes part of every
#: later round's prompt.
MAX_RESULT_CHARS = 24000


#: Reports state and changes nothing.
TIER_READ = "read"
#: Changes the game, not Loopforge's record of it. Writing a script, renaming a
#: scene: the work a person came here to do, and the tier that makes
#: `allow-edit` mean what its name says.
TIER_EDIT = "edit"
#: Produces a record. Work being done, not a claim about it.
TIER_EVIDENCE = "evidence"
#: Asserts something about the project that cites evidence and an approver.
TIER_CLAIM = "claim"

TIERS = (TIER_READ, TIER_EDIT, TIER_EVIDENCE, TIER_CLAIM)

#: How much of a file is worth handing to a model. A source file is a few
#: thousand characters; anything past this is an asset, a log, or a build
#: artifact, and reading it would spend the turn's context on bytes nobody can
#: use.
MAX_FILE_CHARS = 60_000

#: Loopforge's own records. Readable -- `status` and `history` are how, and
#: they are the same bytes -- but never writable through a file tool. The event
#: log is a hash chain and the state is derived from it, so an edit here is not
#: a change to the project, it is a forged history that `loopforge_validate`
#: exists to catch. The Skill says not to; a tool that could is the difference
#: between a rule and a wish.
PROTECTED = ".loopforge"


class Tool:
    """One published command."""

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict[str, Any],
        run: Callable[[LoopforgeProject, dict[str, Any]], Any],
        *,
        tier: str = TIER_READ,
    ) -> None:
        if tier not in TIERS:
            raise ValueError(f"unknown tier: {tier}")
        self.name = name
        self.description = description
        self.schema = schema
        self.run = run
        #: What kind of thing running this is. Decides which exposure rule it
        #: is published under, and it is a property of the command rather than
        #: of the configuration.
        self.tier = tier

    @property
    def mutates(self) -> bool:
        """Whether running this changes anything."""
        return self.tier != TIER_READ

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


def _reconcile(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    apply = arguments.get("apply")
    if not isinstance(apply, bool):
        raise ValueError("apply must be true or false")
    return project.reconcile(apply=apply)


def _init(project: LoopforgeProject, _arguments: dict[str, Any]) -> Any:
    return project.init()


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
    "description": (
        "The revision this change expects. Omit to apply to whatever is current."
    ),
}


#: Files this process has read, absolute. Overwriting a file nobody looked at
#: is how work disappears: the model writes what it believes the file should
#: contain, and whatever was there that it did not know about is gone. Held for
#: the life of the tool server, which is the life of the session.
_SEEN: set[str] = set()


def _inside(project: LoopforgeProject, raw: Any) -> Path:
    """A path in the project, or a refusal naming why it is not.

    Resolved before it is checked, so a symlink pointing out of the project is
    caught rather than followed. The sandbox profile scopes the process to the
    project too; this is the second of the two, and the one that can say
    something useful when it refuses.
    """
    text = str(raw or "").strip()
    if not text:
        raise ValueError("A path is required.")
    root = Path(project.root).resolve()
    candidate = Path(text)
    target = (
        (root / candidate).resolve()
        if not candidate.is_absolute()
        else candidate.resolve()
    )
    if target != root and root not in target.parents:
        raise ValueError(f"{text} is outside the project.")
    return target


def _writable(project: LoopforgeProject, raw: Any) -> Path:
    """The same, and not one of Loopforge's own records."""
    target = _inside(project, raw)
    root = Path(project.root).resolve()
    relative = target.relative_to(root)
    if relative.parts and relative.parts[0] == PROTECTED:
        raise ValueError(
            f"{relative} is Loopforge's own record and is not written by hand. "
            "Use the loopforge_* commands, which keep the event log consistent."
        )
    return target


def _relative(project: LoopforgeProject, target: Path) -> str:
    return str(target.relative_to(Path(project.root).resolve()))


def _list(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    target = _inside(project, arguments.get("path") or ".")
    if not target.is_dir():
        raise ValueError(f"{_relative(project, target)} is not a directory.")
    entries = []
    for child in sorted(
        target.iterdir(), key=lambda item: (not item.is_dir(), item.name)
    ):
        # Hidden files are listed. `.gitignore` and `.editorconfig` are part of
        # a project, and a listing that quietly omits things is a listing a
        # model will draw wrong conclusions from.
        entries.append(
            {
                "path": _relative(project, child),
                "kind": "directory" if child.is_dir() else "file",
                "bytes": child.stat().st_size if child.is_file() else None,
            }
        )
    return {"path": _relative(project, target), "entries": entries}


def _read(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    target = _inside(project, arguments.get("path"))
    if not target.is_file():
        raise ValueError(f"{_relative(project, target)} is not a file.")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        # Named rather than mangled. A model handed replacement characters
        # would try to edit them back.
        raise ValueError(
            f"{_relative(project, target)} is not text; it cannot be read this way."
        ) from error
    _SEEN.add(str(target))
    if len(text) > MAX_FILE_CHARS:
        # Truncated visibly, and editing is still safe: `loopforge_edit`
        # matches a string rather than a region, so a model that only saw the
        # head can still change something it did see.
        return {
            "path": _relative(project, target),
            "content": text[:MAX_FILE_CHARS],
            "truncated": True,
            "total_characters": len(text),
        }
    return {"path": _relative(project, target), "content": text, "truncated": False}


def _write(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    target = _writable(project, arguments.get("path"))
    content = arguments.get("content")
    if not isinstance(content, str):
        raise ValueError("content must be text.")
    existed = target.is_file()
    if existed and str(target) not in _SEEN:
        # The one refusal that is about the person rather than the model.
        # Overwriting a file nobody looked at replaces whatever it held with
        # what the model believes it should hold, and the difference is work
        # that is simply gone.
        raise ValueError(
            f"{_relative(project, target)} already exists and has not been read. "
            "Read it first, then write it -- or use loopforge_edit to change "
            "part of it."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _SEEN.add(str(target))
    return {
        "path": _relative(project, target),
        "created": not existed,
        "characters": len(content),
    }


def _edit(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    target = _writable(project, arguments.get("path"))
    old = arguments.get("old_string")
    new = arguments.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        raise ValueError("old_string and new_string must both be text.")
    if not old:
        raise ValueError(
            "old_string must not be empty; use loopforge_write for a new file."
        )
    if not target.is_file():
        raise ValueError(f"{_relative(project, target)} is not a file.")
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    if found == 0:
        raise ValueError(f"old_string does not appear in {_relative(project, target)}.")
    if found > 1:
        # Refused rather than guessed. Replacing the first of several is how an
        # edit lands somewhere the model did not mean, and it is invisible
        # afterwards -- the file still compiles and says something else.
        raise ValueError(
            f"old_string appears {found} times in {_relative(project, target)}. "
            "Include enough surrounding lines to name one of them."
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    _SEEN.add(str(target))
    return {"path": _relative(project, target), "replaced": 1}


def _ask(project: LoopforgeProject, arguments: dict[str, Any]) -> Any:
    """Put a question to the person, and wait for their answer.

    The model used to ask in prose -- "A. ... B. ... C. ... Which?" -- and the
    person answered by typing "A", guessing what that still meant to a model
    that had moved on. Nothing structured was left behind: no record of what
    was offered, and no way for a surface to tell a question from a paragraph.

    Blocking is the point. A tool call that returned "I have asked" would put
    the model straight back to guessing, and it is the same shape as an
    approval: the call is held open, a person decides, and the decision is the
    result.
    """
    import time

    from .agent.questions_bridge import QuestionBridge

    bridge = QuestionBridge(project.root)
    record = bridge.ask(
        arguments.get("question"),
        arguments.get("options"),
        bool(arguments.get("allow_free_text", False)),
    )
    deadline = time.monotonic() + bridge.wait_seconds
    while time.monotonic() < deadline:
        answer = bridge.answer_of(record["question_id"])
        if answer is not None:
            return {
                "question_id": record["question_id"],
                "answered": True,
                "answer": answer,
            }
        time.sleep(bridge.poll_seconds)
    bridge.withdraw(record["question_id"])
    # Reported rather than raised. A question nobody answered is something the
    # model has to work around -- by asking again, or by choosing a default and
    # saying so -- and a failed tool call would read to it as a broken tool.
    return {
        "question_id": record["question_id"],
        "answered": False,
        "answer": "",
        "note": (
            "Nobody answered in time. Do not assume an answer; ask again or "
            "say what you will do without one."
        ),
    }


TOOLS: tuple[Tool, ...] = (
    Tool(
        "loopforge_list",
        "What is in a directory of the project. Use this to find your way "
        "around before reading or writing anything.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Project-relative directory. Defaults to the project root."
                    ),
                }
            },
        },
        _list,
    ),
    Tool(
        "loopforge_read",
        "Read a text file from the project. Read a file before you change it: "
        "writing over one you have not read replaces whatever it held.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project-relative file path."}
            },
            "required": ["path"],
        },
        _read,
    ),
    Tool(
        "loopforge_write",
        "Create a file, or replace one entirely. Prefer `loopforge_edit` for a "
        "change to part of an existing file -- this replaces the whole of it. "
        "You cannot write inside `.loopforge`; those are Loopforge's own "
        "records and the loopforge_* commands keep them consistent.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project-relative file path.",
                },
                "content": {
                    "type": "string",
                    "description": "The whole contents of the file.",
                },
            },
            "required": ["path", "content"],
        },
        _write,
        tier=TIER_EDIT,
    ),
    Tool(
        "loopforge_edit",
        "Change part of a file by replacing an exact string. `old_string` must "
        "appear exactly once -- include surrounding lines until it does.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project-relative file path.",
                },
                "old_string": {
                    "type": "string",
                    "description": (
                        "The text to replace, exactly as it appears, appearing once."
                    ),
                },
                "new_string": {
                    "type": "string",
                    "description": "What to put there instead.",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
        _edit,
        tier=TIER_EDIT,
    ),
    Tool(
        "loopforge_ask",
        "REQUIRED for any question you need answered. Asks the person and "
        "blocks until they answer, then returns what they said. Use this "
        "instead of ending your reply with a question -- a question in a reply "
        "makes them type an answer to a message you have already moved past, "
        "and a lettered list makes them type a letter. Supply `options` when "
        "there is a set of answers you can name; they can still answer in "
        "their own words.",
        {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "What you need to know, in one sentence.",
                },
                "options": {
                    "type": "array",
                    "description": "The answers you can name, if any.",
                    "items": {"type": "string"},
                },
                "allow_free_text": {
                    "type": "boolean",
                    "description": (
                        "Whether they may answer in their own words as well."
                    ),
                },
            },
            "required": ["question"],
        },
        _ask,
        # Read, so it is never gated behind an approval. Asking a person is not
        # a change to the project, and putting a "may the agent ask you
        # something?" prompt in front of the question would be absurd.
        tier=TIER_READ,
    ),
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
    Tool(
        "loopforge_reconcile",
        "Preview or apply rebuilding the derived state snapshot from intact "
        "event history. Always call with apply=false first and inspect the "
        "actions; use apply=true only when validation found no history or "
        "artifact integrity error.",
        {
            "type": "object",
            "properties": {
                "apply": {
                    "type": "boolean",
                    "description": "False previews the rebuild; true applies it.",
                }
            },
            "required": ["apply"],
        },
        _reconcile,
        tier=TIER_EVIDENCE,
    ),
    # -- changing it ------------------------------------------------------
    #
    # Each of these is published under `approval_required`: the runtime asks a
    # person, naming the tool and the arguments, and runs the call only if they
    # say yes.
    Tool(
        "loopforge_init",
        "Set up Loopforge state in this project directory. Safe to call when it "
        "is already set up: it reports the existing state rather than replacing "
        "it.",
        NO_ARGUMENTS,
        _init,
        # Creates durable state and asserts nothing about the game. It was
        # unpublished while nothing mutating was, and stayed unpublished after
        # -- so the context said the project was uninitialized and named `init`
        # as the next action, and the model had no way to take it. It said it
        # was running the command instead, which is the only thing left.
        tier=TIER_EVIDENCE,
    ),
    Tool(
        "loopforge_gate",
        "Check whether the project satisfies the gate into a stage, without "
        "moving it. Reports which requirements are unmet.",
        {
            "type": "object",
            "properties": {"target_stage": STAGE},
            "required": ["target_stage"],
        },
        # Reads. `gate_check` computes requirements from current state and
        # writes nothing -- it was marked as a mutation, which would have cost
        # a person an approval prompt for asking a question.
        _gate,
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
        tier=TIER_EVIDENCE,
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
        tier=TIER_EVIDENCE,
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
        tier=TIER_CLAIM,
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
    return text[:MAX_RESULT_CHARS] + f"… [truncated at {MAX_RESULT_CHARS} characters]"


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
                "result": {
                    **_text_result(f"{type(error).__name__}: {error}"),
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _text_result(_bounded(payload)),
        }

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
