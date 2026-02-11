from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.preview_manifest import load_screens_manifest  # noqa: E402
from migrator.preview_sync import sync_preview_host  # noqa: E402


class TestPreviewSync(unittest.TestCase):
    def test_sync_preview_host_updates_manifest_and_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            generated_dir = workspace / "generated" / "frontend" / "src" / "screens"
            preview_host_dir = workspace / "preview-host"
            manifest_path = preview_host_dir / "src" / "manifest" / "screens.manifest.json"
            registry_generated_path = (
                preview_host_dir / "src" / "screens" / "registry.generated.ts"
            )

            (generated_dir / "orders").mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "manifest").mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "screens").mkdir(parents=True, exist_ok=True)

            dashboard_file = generated_dir / "Dashboard.tsx"
            dashboard_file.write_text(
                "export default function Dashboard() { return null; }\n",
                encoding="utf-8",
            )
            dashboard_file.with_suffix(".preview.json").write_text(
                json.dumps(
                    {
                        "screenId": "dashboard_home",
                        "title": "Dashboard Home",
                        "sourceXmlPath": "legacy/screens/dashboard.xml",
                        "sourceNodePath": "/Screen[1]/Layouts[1]",
                    }
                ),
                encoding="utf-8",
            )

            order_list_file = generated_dir / "orders" / "OrderList.tsx"
            order_list_file.write_text(
                "export default function OrderList() { return null; }\n",
                encoding="utf-8",
            )

            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "./screens.manifest.schema.json",
                        "schemaVersion": "1.0",
                        "generatedAtUtc": "2026-02-11T00:00:00Z",
                        "screens": [
                            {
                                "screenId": "simple_screen",
                                "title": "Simple Screen (Placeholder)",
                                "entryModule": "screens/placeholder/PlaceholderScreen",
                                "sourceXmlPath": "tests/fixtures/simple_screen_fixture.txt",
                                "sourceNodePath": "/Screen[1]",
                            },
                            {
                                "screenId": "stale_generated",
                                "entryModule": "screens/generated/StaleScreen",
                                "sourceXmlPath": "generated/frontend/src/screens/StaleScreen.tsx",
                                "sourceNodePath": "/generated/screens/stale_generated",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = sync_preview_host(
                generated_screens_dir=generated_dir,
                preview_host_dir=preview_host_dir,
            )

            self.assertEqual(report.preserved_screen_count, 1)
            self.assertEqual(report.generated_screen_count, 2)
            self.assertIn("dashboard_home", report.generated_screen_ids)
            self.assertIn("orders-OrderList", report.generated_screen_ids)
            self.assertEqual(report.warnings, [])

            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            parsed_manifest = load_screens_manifest(manifest_payload)
            self.assertEqual(parsed_manifest.schema_version, "1.0")
            self.assertEqual(len(parsed_manifest.screens), 3)
            self.assertIsNotNone(parsed_manifest.find_screen("simple_screen"))
            self.assertIsNotNone(parsed_manifest.find_screen("dashboard_home"))
            self.assertIsNotNone(parsed_manifest.find_screen("orders-OrderList"))
            self.assertIsNone(parsed_manifest.find_screen("stale_generated"))

            dashboard_entry = parsed_manifest.find_screen("dashboard_home")
            if dashboard_entry is None:
                raise AssertionError("Expected dashboard_home screen entry.")
            self.assertEqual(dashboard_entry.title, "Dashboard Home")
            self.assertEqual(
                dashboard_entry.source_xml_path,
                "legacy/screens/dashboard.xml",
            )
            self.assertEqual(
                dashboard_entry.source_node_path,
                "/Screen[1]/Layouts[1]",
            )
            self.assertEqual(
                dashboard_entry.entry_module,
                "screens/generated/Dashboard",
            )

            order_entry = parsed_manifest.find_screen("orders-OrderList")
            if order_entry is None:
                raise AssertionError("Expected orders-OrderList screen entry.")
            self.assertEqual(
                order_entry.source_xml_path,
                "generated/frontend/src/screens/orders/OrderList.tsx",
            )
            self.assertEqual(
                order_entry.source_node_path,
                "/generated/screens/orders-OrderList",
            )
            self.assertEqual(
                order_entry.entry_module,
                "screens/generated/orders/OrderList",
            )

            registry_text = registry_generated_path.read_text(encoding="utf-8")
            self.assertIn(
                '"screens/generated/Dashboard": () => import("../../../generated/frontend/src/screens/Dashboard"),',
                registry_text,
            )
            self.assertIn(
                '"screens/generated/orders/OrderList": () => import("../../../generated/frontend/src/screens/orders/OrderList"),',
                registry_text,
            )
            self.assertNotIn("StaleScreen", registry_text)

    def test_sync_preview_host_with_no_generated_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            generated_dir = workspace / "generated" / "frontend" / "src" / "screens"
            preview_host_dir = workspace / "preview-host"
            manifest_path = preview_host_dir / "src" / "manifest" / "screens.manifest.json"
            registry_generated_path = (
                preview_host_dir / "src" / "screens" / "registry.generated.ts"
            )

            generated_dir.mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "manifest").mkdir(parents=True, exist_ok=True)

            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "./screens.manifest.schema.json",
                        "schemaVersion": "1.0",
                        "generatedAtUtc": "2026-02-11T00:00:00Z",
                        "screens": [
                            {
                                "screenId": "simple_screen",
                                "entryModule": "screens/placeholder/PlaceholderScreen",
                                "sourceXmlPath": "tests/fixtures/simple_screen_fixture.txt",
                                "sourceNodePath": "/Screen[1]",
                            },
                            {
                                "screenId": "stale_generated",
                                "entryModule": "screens/generated/StaleScreen",
                                "sourceXmlPath": "generated/frontend/src/screens/StaleScreen.tsx",
                                "sourceNodePath": "/generated/screens/stale_generated",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = sync_preview_host(
                generated_screens_dir=generated_dir,
                preview_host_dir=preview_host_dir,
            )

            self.assertEqual(report.preserved_screen_count, 1)
            self.assertEqual(report.generated_screen_count, 0)
            self.assertEqual(report.generated_screen_ids, [])
            self.assertEqual(report.warnings, ["No generated screen modules were found."])

            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            parsed_manifest = load_screens_manifest(manifest_payload)
            self.assertEqual(len(parsed_manifest.screens), 1)
            self.assertIsNotNone(parsed_manifest.find_screen("simple_screen"))
            self.assertIsNone(parsed_manifest.find_screen("stale_generated"))

            registry_text = registry_generated_path.read_text(encoding="utf-8")
            self.assertIn(
                "export const generatedScreenModuleLoaders: Record<string, ScreenModuleLoader> = {",
                registry_text,
            )
            self.assertNotIn('import("', registry_text)


if __name__ == "__main__":
    unittest.main()
