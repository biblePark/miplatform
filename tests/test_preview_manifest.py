from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.preview_manifest import (  # noqa: E402
    ManifestContractError,
    load_screens_manifest,
    load_screens_manifest_file,
)


FIXTURE_MANIFEST = Path(__file__).parent / "fixtures" / "screens_manifest_valid.json"


class TestPreviewManifest(unittest.TestCase):
    def test_load_manifest_file_success(self) -> None:
        manifest = load_screens_manifest_file(FIXTURE_MANIFEST)

        self.assertEqual(manifest.schema_version, "1.0")
        self.assertEqual(manifest.generated_at_utc, "2026-02-11T00:00:00Z")
        self.assertEqual(len(manifest.screens), 1)

        screen = manifest.find_screen("simple_screen")
        self.assertIsNotNone(screen)
        if screen is None:  # pragma: no cover - type-narrow guard
            raise AssertionError("Expected simple_screen manifest entry.")
        self.assertEqual(screen.entry_module, "screens/placeholder/PlaceholderScreen")
        self.assertEqual(screen.preview_route(), "/preview/simple_screen")

    def test_duplicate_screen_id_fails(self) -> None:
        payload = {
            "schemaVersion": "1.0",
            "generatedAtUtc": "2026-02-11T00:00:00Z",
            "screens": [
                {
                    "screenId": "dup_screen",
                    "entryModule": "screens/placeholder/PlaceholderScreen",
                    "sourceXmlPath": "a.xml",
                    "sourceNodePath": "/Screen[1]",
                },
                {
                    "screenId": "dup_screen",
                    "entryModule": "screens/placeholder/PlaceholderScreen",
                    "sourceXmlPath": "b.xml",
                    "sourceNodePath": "/Screen[1]",
                },
            ],
        }

        with self.assertRaises(ManifestContractError):
            load_screens_manifest(payload)

    def test_entry_module_contract_violation_fails(self) -> None:
        payload = {
            "schemaVersion": "1.0",
            "generatedAtUtc": "2026-02-11T00:00:00Z",
            "screens": [
                {
                    "screenId": "simple_screen",
                    "entryModule": "../outside/module",
                    "sourceXmlPath": "a.xml",
                    "sourceNodePath": "/Screen[1]",
                }
            ],
        }

        with self.assertRaises(ManifestContractError):
            load_screens_manifest(payload)

    def test_missing_required_field_fails(self) -> None:
        payload = {
            "schemaVersion": "1.0",
            "generatedAtUtc": "2026-02-11T00:00:00Z",
            "screens": [{"screenId": "simple_screen"}],
        }

        with self.assertRaises(ManifestContractError):
            load_screens_manifest(payload)


if __name__ == "__main__":
    unittest.main()
