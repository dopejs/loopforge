from __future__ import annotations

import binascii
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "skills" / "direct-game-art" / "scripts" / "validate_manifest.py"


def png_rgba(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def checksum(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class DirectGameArtManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.manifest_path = self.project / "asset-manifest.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def asset(self, *, status: str = "planned") -> dict[str, object]:
        return {
            "id": "hero-idle",
            "family": "character",
            "role": "canonical player idle",
            "status": status,
            "runtime_path": "assets/runtime/hero.png",
            "source_path": "assets/raw/hero.png",
            "curated_path": "assets/curated/hero.png",
            "format": "png",
            "dimensions": {"width": 1, "height": 1},
            "max_bytes": 4096,
            "checksum": "",
            "alpha": "required",
            "variants": [],
            "runtime": {
                "display_size": "64x64 px",
                "pivot": "0.5,1.0",
                "frames": 1,
                "fps": 0,
                "loop": False,
            },
            "provenance": {
                "source_kind": "generated",
                "source_uri": "project://art-generation/hero-idle",
                "creator_or_provider": "configured image provider",
                "model_or_version": "provider-model-v1",
                "acquired_at": "2026-08-18",
                "license": "proprietary",
                "parent_asset_ids": [],
                "transformations": [],
            },
        }

    def manifest(
        self, *, approved: bool = True, asset: dict[str, object] | None = None
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "project_identity": "git:abc123",
            "representative_target": {
                "id": "target-main",
                "revision": 1,
                "approval": {
                    "status": "approved" if approved else "pending",
                    "approver_id": "user-1" if approved else "",
                    "approver_name": "Art owner" if approved else "",
                    "rationale": "Target proves hierarchy at runtime scale."
                    if approved
                    else "",
                },
            },
            "assets": [asset or self.asset()],
        }

    def validate(
        self, document: dict[str, object], *extra: str
    ) -> subprocess.CompletedProcess[str]:
        self.manifest_path.write_text(json.dumps(document), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--project",
                str(self.project),
                "--manifest",
                str(self.manifest_path),
                "--format",
                "json",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_approved_planned_manifest_is_valid_without_generated_files(self) -> None:
        result = self.validate(self.manifest(), "--require-approved")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_pending_target_blocks_approved_production_gate(self) -> None:
        result = self.validate(self.manifest(approved=False), "--require-approved")
        self.assertEqual(result.returncode, 2)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("TARGET_NOT_APPROVED", codes)

    def test_asset_paths_cannot_escape_project(self) -> None:
        asset = self.asset()
        asset["runtime_path"] = "../outside.png"
        result = self.validate(self.manifest(asset=asset))
        self.assertEqual(result.returncode, 2)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("ASSET_PATH_INVALID", codes)

    def test_duplicate_and_unknown_parent_ids_are_rejected(self) -> None:
        first = self.asset()
        first["provenance"]["parent_asset_ids"] = ["missing-parent"]  # type: ignore[index]
        second = self.asset()
        document = self.manifest(asset=first)
        document["assets"] = [first, second]
        result = self.validate(document)
        self.assertEqual(result.returncode, 2)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("ASSET_IDS_DUPLICATE", codes)
        self.assertIn("ASSET_PARENT_UNKNOWN", codes)

    def test_runtime_png_checks_files_dimensions_alpha_size_and_checksum(self) -> None:
        data = png_rgba(1, 1)
        for relative in (
            "assets/raw/hero.png",
            "assets/curated/hero.png",
            "assets/runtime/hero.png",
        ):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        asset = self.asset(status="runtime")
        asset["checksum"] = checksum(data)
        result = self.validate(self.manifest(asset=asset), "--require-approved")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_runtime_dimension_and_checksum_mismatch_are_rejected(self) -> None:
        data = png_rgba(2, 1)
        for relative in (
            "assets/raw/hero.png",
            "assets/curated/hero.png",
            "assets/runtime/hero.png",
        ):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        asset = self.asset(status="runtime")
        asset["checksum"] = "sha256:" + "0" * 64
        result = self.validate(self.manifest(asset=asset))
        self.assertEqual(result.returncode, 2)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("ASSET_DIMENSIONS_MISMATCH", codes)
        self.assertIn("ASSET_CHECKSUM_MISMATCH", codes)

    def test_template_placeholders_are_rejected(self) -> None:
        template = (
            ROOT / "skills" / "direct-game-art" / "assets" / "asset-manifest.json"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--project",
                str(ROOT),
                "--manifest",
                str(template),
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("MANIFEST_PLACEHOLDERS_REMAIN", codes)


if __name__ == "__main__":
    unittest.main()
