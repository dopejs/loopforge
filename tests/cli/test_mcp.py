"""The MCP server that lets an agent run Loopforge's commands instead of
describing them.

Two things carry the weight here. The framing has to be exact, because a
malformed frame does not fail loudly -- it desynchronises the stream and every
later answer is read as part of the wrong message. And the published set has to
stay read-only: Loopforge's claim is that a stage transition cites evidence and
records a human approver, and a tool that let a model advance a stage on its own
would make that claim false while leaving the record looking correct.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from loopforge.mcp import MAX_RESULT_CHARS, TOOLS, read_frame, respond, serve
from loopforge.project import LoopforgeProject


def frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def frames(raw: bytes) -> list[dict]:
    """Every message in a response stream, parsed the way a reader must."""
    stream = io.BytesIO(raw)
    found = []
    while True:
        payload = read_frame(stream)
        if payload is None:
            return found
        if payload:
            found.append(json.loads(payload))


class McpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_server(self, *requests: dict) -> list[dict]:
        stdin = io.BytesIO(b"".join(frame(request) for request in requests))
        stdout = io.BytesIO()
        serve(self.root, stdin, stdout)
        return frames(stdout.getvalue())

    def call(self, name: str, **arguments) -> dict:
        answered = self.run_server(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return answered[0]["result"]

    # -- protocol ----------------------------------------------------------

    def test_several_requests_in_one_stream_get_several_answers(self) -> None:
        """Reading past a frame would consume the start of the next one.

        The failure is not a crash: the stream desynchronises and every later
        answer is read as part of the wrong message.
        """
        answered = self.run_server(
            {"jsonrpc": "2.0", "id": "1", "method": "initialize"},
            {"jsonrpc": "2.0", "id": "2", "method": "tools/list"},
            {"jsonrpc": "2.0", "id": "3", "method": "tools/list"},
        )

        self.assertEqual([answer["id"] for answer in answered], ["1", "2", "3"])

    def test_a_notification_is_not_answered(self) -> None:
        """A request with no id has nothing to answer under."""
        self.assertEqual(self.run_server({"jsonrpc": "2.0", "method": "initialized"}), [])

    def test_an_unknown_method_is_a_protocol_error(self) -> None:
        answered = self.run_server({"jsonrpc": "2.0", "id": "1", "method": "resources/list"})

        self.assertEqual(answered[0]["error"]["code"], -32601)

    # -- what is published -------------------------------------------------

    def test_every_tool_declares_the_arguments_it_takes(self) -> None:
        """A model cannot call a tool whose shape it was not told.

        Absent is not the same as "takes nothing": a tool with no arguments
        still declares an object with no properties.
        """
        for tool in TOOLS:
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.schema.get("type"), "object")
                self.assertIn("properties", tool.schema)
                self.assertTrue(tool.description.strip())

    def test_every_command_that_changes_state_says_so(self) -> None:
        """The boundary this file exists to hold.

        A stage transition cites evidence and records a human approver. What
        makes that true is the tier declared here -- on the command rather than
        in whoever writes the exposure rules, so a misconfigured rule cannot
        turn one kind into another. Which tiers are asked about is the
        permission mode's business, and covered with it.
        """
        by_name = {tool.name: tool for tool in TOOLS}
        for name in ("loopforge_advance", "loopforge_run", "loopforge_capture", "loopforge_init"):
            with self.subTest(tool=name):
                self.assertIn(name, by_name)
                self.assertTrue(by_name[name].mutates, f"{name} changes the project")

    def test_reading_state_is_not_marked_as_changing_it(self) -> None:
        """Asking a person about a read is how a person stops reading the
        questions. `gate` is here because it computes requirements and writes
        nothing -- marked as a mutation it cost an approval prompt for asking a
        question."""
        by_name = {tool.name: tool for tool in TOOLS}
        for name in (
            "loopforge_status",
            "loopforge_inspect",
            "loopforge_history",
            "loopforge_validate",
            "loopforge_gate",
        ):
            with self.subTest(tool=name):
                self.assertFalse(by_name[name].mutates)

    def test_the_commands_that_make_a_claim_are_still_unpublished(self) -> None:
        """`decide` records that a prototype is kept or killed, and a playtest
        report is an account of what a person observed. Neither is something a
        model may enter on their behalf, whoever approves the call."""
        published = {tool.name for tool in TOOLS}
        self.assertEqual(
            published & {"loopforge_decide", "loopforge_playtest", "loopforge_evidence"},
            set(),
        )

    # -- calling -----------------------------------------------------------

    def test_status_answers_from_the_project(self) -> None:
        LoopforgeProject(self.root).init()

        result = self.call("loopforge_status")

        self.assertNotIn("isError", result)
        answer = json.loads(result["content"][0]["text"])
        self.assertEqual(answer["stage"], "DISCOVERY")

    def test_inspect_reports_the_engine_it_detects(self) -> None:
        (self.root / "project.godot").write_text("[application]\n", encoding="utf-8")

        answer = json.loads(self.call("loopforge_inspect")["content"][0]["text"])

        self.assertEqual(answer["engine_detections"][0]["engine"], "godot")

    def test_history_can_be_asked_for_only_the_recent_events(self) -> None:
        LoopforgeProject(self.root).init()

        answer = json.loads(self.call("loopforge_history", limit=1)["content"][0]["text"])

        self.assertEqual(len(answer["events"]), 1)

    def test_an_unknown_tool_is_reported_rather_than_raised(self) -> None:
        """It named a tool that does not exist and can name a real one next
        round; killing the server would end the turn instead."""
        result = self.call("loopforge_delete_everything")

        self.assertTrue(result["isError"])
        self.assertIn("no such tool", result["content"][0]["text"])

    def test_a_command_that_refuses_is_an_answer(self) -> None:
        """An uninitialized project is the ordinary case, and the model has to
        be told which failure it is rather than seeing the server die."""
        result = self.call("loopforge_validate")

        self.assertTrue(result["isError"])
        self.assertTrue(result["content"][0]["text"].strip())

    def test_a_long_answer_says_that_it_was_cut(self) -> None:
        """A silently shortened result reads as the whole answer, and a model
        would reason from a project state missing its tail without knowing."""
        LoopforgeProject(self.root).init()
        long_events = [{"filler": "x" * 200} for _ in range(400)]
        with unittest.mock.patch.object(
            LoopforgeProject, "history", return_value={"events": long_events}
        ):
            text = self.call("loopforge_history")["content"][0]["text"]

        self.assertLess(len(text), MAX_RESULT_CHARS + 100)
        self.assertIn("truncated", text)


class ExposureRuleTests(unittest.TestCase):
    """What the supervisor publishes each tool under."""

    def test_the_tier_of_every_published_tool_is_known(self) -> None:
        from loopforge.agent.supervisor import KuraRuntimeSupervisor

        tiers = KuraRuntimeSupervisor._tool_tiers()

        self.assertEqual(tiers["loopforge_advance"], "claim")
        self.assertEqual(tiers["loopforge_run"], "evidence")
        self.assertEqual(tiers["loopforge_status"], "read")

    def test_unreadable_definitions_ask_about_everything(self) -> None:
        """`None` means "could not tell", and every tool is then unplaceable --
        which every mode answers by asking. An empty mapping would do the same
        thing silently."""
        from loopforge.agent.supervisor import KuraRuntimeSupervisor
        from loopforge.permissions import MODES, exposure_for

        with unittest.mock.patch.dict("sys.modules", {"loopforge.mcp": None}):
            self.assertIsNone(KuraRuntimeSupervisor._tool_tiers())
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertEqual(exposure_for("unrecognized", mode), "approval_required")


class PublishedSurfaceTests(unittest.TestCase):
    """Every action the context names must be one the model can take."""

    def test_the_actions_the_context_offers_are_all_published(self) -> None:
        """The gap a person sees first.

        The project context names `init` as the next action and the router
        tells the model to take it. It was not published, so the model said it
        was running the command -- which is the honest thing to do when you are
        told to run one and cannot. An instruction the tools cannot satisfy is
        worse than a missing tool: it produces a confident account of work that
        did not happen.
        """
        published = {tool.name for tool in TOOLS}
        for action in ("init", "gate", "advance"):
            with self.subTest(action=action):
                self.assertIn(f"loopforge_{action}", published)

    def test_the_router_tells_the_model_to_call_tools(self) -> None:
        """It told the model to run shell commands, which it cannot do. That
        one instruction is why every answer was a narration."""
        from pathlib import Path as _Path

        router = _Path(__file__).resolve().parents[2] / "skills" / "loopforge-router" / "SKILL.md"
        text = router.read_text(encoding="utf-8")

        self.assertIn("loopforge_inspect", text)
        self.assertIn("loopforge_init", text)
        # No instruction to run a command. The one surviving mention is the
        # sentence telling the model not to write one out.
        instructions = [
            line
            for line in text.splitlines()
            if "`loopforge " in line and "Running" not in line
        ]
        self.assertEqual(instructions, [], f"still tells the model to run commands: {instructions}")
