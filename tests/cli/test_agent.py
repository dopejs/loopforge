from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from loopforge.agent.contracts import build_project_context, project_id
from loopforge.agent.kura_client import KuraAgentError, KuraClient
from loopforge.agent.supervisor import AgentSupervisor
from loopforge.cli import build_command_parser
from loopforge.errors import InvalidStateError, LoopforgeError
from loopforge.project import LoopforgeProject


class AgentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = LoopforgeProject(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_uninitialized_context_is_stable_and_redacted(self) -> None:
        context = build_project_context(self.project)
        self.assertEqual(context["schema_version"], "game-project-context-v1")
        self.assertEqual(context["project_id"], project_id(self.root))
        self.assertEqual(context["stage"], "UNINITIALIZED")
        self.assertEqual(context["observed_revision"], 0)
        self.assertNotIn("environment", context)
        self.assertIn("access_tokens", context["redactions"])

    def test_initialized_context_tracks_project_revision(self) -> None:
        self.project.init()
        context = build_project_context(self.project)
        self.assertEqual(context["stage"], "DISCOVERY")
        self.assertEqual(context["observed_revision"], 1)
        self.assertEqual(
            context["next_actions"], ["hypothesis create", "gate check PROTOTYPING"]
        )

    def test_status_does_not_probe_an_unmanaged_global_daemon(self) -> None:
        supervisor = AgentSupervisor(self.project, dope_binary="/bin/false")
        self.assertEqual(
            supervisor.status(),
            {
                "running": False,
                "healthy": False,
                "managed": False,
                "base_url": None,
                # No pairing token without a managed daemon.
                "token": None,
            },
        )

    def test_start_uses_project_local_test_environment_and_syncs_later(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> object:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return type(
                "Completed", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()

        supervisor = AgentSupervisor(self.project, dope_binary="/tmp/dope-cli")
        with (
            patch("loopforge.agent.supervisor.subprocess.run", side_effect=fake_run),
            patch.object(
                supervisor,
                "status",
                side_effect=[
                    {"running": False, "healthy": False},
                    {
                        "running": True,
                        "healthy": True,
                        "base_url": "http://127.0.0.1:19999",
                    },
                ],
            ),
        ):
            result = supervisor.start(19999)

        self.assertTrue(result["healthy"])
        environment = captured["kwargs"]["env"]  # type: ignore[index]
        # Kura's embedded shape: the host owns the process, the data dir and
        # the port. Isolation matches the test environment without borrowing
        # its "this is a developer daemon" semantics.
        self.assertEqual(environment["KURA_ENV"], "embedded")
        self.assertEqual(environment["KURA_BIND_ADDR"], "127.0.0.1:19999")
        self.assertTrue(environment["KURA_DATA_DIR"].endswith(".loopforge/agent/data"))
        metadata = json.loads(supervisor.metadata_path.read_text())
        self.assertEqual(metadata["schema_version"], "kura-runtime-v1")
        self.assertNotEqual(environment["KURA_DATA_DIR"], os.path.expanduser("~/.dope"))

    def test_runtime_metadata_rejects_non_loopback_and_unexpected_data_dir(
        self,
    ) -> None:
        supervisor = AgentSupervisor(self.project, dope_binary="/bin/false")
        supervisor.root.mkdir(parents=True)
        invalid_values = [
            {
                "schema_version": "kura-runtime-v1",
                "bind_addr": "10.0.0.1:19192",
                "data_dir": str(supervisor.root / "data"),
            },
            {
                "schema_version": "kura-runtime-v1",
                "bind_addr": "127.0.0.1:19192",
                "data_dir": str(self.root / "outside"),
            },
            {
                "schema_version": "agent-runtime-v1",
                "bind_addr": "127.0.0.1:19192",
                "data_dir": str(supervisor.root / "data"),
            },
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                supervisor.metadata_path.write_text(json.dumps(value))
                with self.assertRaises(InvalidStateError):
                    supervisor.status()

    def test_kura_client_only_accepts_loopback_http_origins(self) -> None:
        self.assertEqual(
            KuraClient("http://127.0.0.1:19192/").base_url,
            "http://127.0.0.1:19192",
        )
        self.assertEqual(
            KuraClient("http://[::1]:19192").base_url,
            "http://[::1]:19192",
        )
        for value in (
            "https://127.0.0.1:19192",
            "http://10.0.0.1:19192",
            "http://127.0.0.1:19192@evil.example",
            "http://127.0.0.1:19192/path",
            "http://127.0.0.1",
        ):
            with self.subTest(value=value), self.assertRaises(KuraAgentError):
                KuraClient(value)

    def test_failed_health_check_stops_daemon_and_removes_metadata(self) -> None:
        supervisor = AgentSupervisor(self.project, dope_binary="/tmp/dope-cli")
        completed = type(
            "Completed", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )()
        with (
            patch(
                "loopforge.agent.supervisor.subprocess.run", return_value=completed
            ) as run,
            patch.object(
                supervisor,
                "status",
                side_effect=[
                    {"running": False, "healthy": False},
                    {"running": False, "healthy": False, "reason": "not ready"},
                ],
            ),
        ):
            with self.assertRaisesRegex(LoopforgeError, "did not become healthy"):
                supervisor.start(19999)

        self.assertEqual(run.call_count, 2)
        self.assertFalse(supervisor.metadata_path.exists())

    def test_stop_and_doctor_accept_the_same_binary_override_as_start(self) -> None:
        parser = build_command_parser()
        for command in ("start", "stop", "doctor"):
            with self.subTest(command=command):
                parsed = parser.parse_args(
                    ["agent", command, "--dope-binary", "/tmp/dope-cli"]
                )
                self.assertEqual(parsed.kura_binary, "/tmp/dope-cli")

    def test_sync_persists_context_in_the_loopforge_project(self) -> None:
        self.project.init()
        supervisor = AgentSupervisor(self.project, dope_binary="/bin/false")

        result = supervisor.sync_context()

        self.assertTrue(result["synchronized"])
        self.assertEqual(result["context_path"], str(supervisor.context_path))
        self.assertEqual(
            json.loads(supervisor.context_path.read_text()), result["context"]
        )
        self.assertEqual(result["context"]["stage"], "DISCOVERY")


if __name__ == "__main__":
    unittest.main()
