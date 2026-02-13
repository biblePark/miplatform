from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.preview_smoke import smoke_preview_host  # noqa: E402


class TestPreviewSmoke(unittest.TestCase):
    def test_smoke_preview_host_emits_deterministic_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            generated_dir = workspace / "generated" / "frontend" / "src" / "screens"
            preview_host_dir = workspace / "preview-host"
            manifest_path = preview_host_dir / "src" / "manifest" / "screens.manifest.json"
            registry_generated_path = (
                preview_host_dir / "src" / "screens" / "registry.generated.ts"
            )

            (generated_dir / "reports").mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "manifest").mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "screens").mkdir(parents=True, exist_ok=True)

            (generated_dir / "Orders.tsx").write_text(
                "export default function Orders() { return null; }\n",
                encoding="utf-8",
            )
            (generated_dir / "reports" / "Detail.tsx").write_text(
                "export default function Detail() { return null; }\n",
                encoding="utf-8",
            )

            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "./screens.manifest.schema.json",
                        "schemaVersion": "1.0",
                        "generatedAtUtc": "2026-02-12T00:00:00Z",
                        "screens": [
                            {
                                "screenId": "simple_screen",
                                "entryModule": "screens/placeholder/PlaceholderScreen",
                                "sourceXmlPath": "tests/fixtures/simple_screen_fixture.txt",
                                "sourceNodePath": "/Screen[1]",
                            },
                            {
                                "screenId": "orders",
                                "entryModule": "screens/generated/Orders",
                                "sourceXmlPath": "generated/frontend/src/screens/Orders.tsx",
                                "sourceNodePath": "/generated/screens/orders",
                            },
                            {
                                "screenId": "reports-Detail",
                                "entryModule": "screens/generated/reports/Detail",
                                "sourceXmlPath": "generated/frontend/src/screens/reports/Detail.tsx",
                                "sourceNodePath": "/generated/screens/reports-Detail",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            registry_generated_path.write_text(
                "\n".join(
                    [
                        "/* Auto-generated */",
                        'import type { ScreenModuleLoader } from "../manifest/types";',
                        "",
                        "export const generatedScreenModuleLoaders: Record<string, ScreenModuleLoader> = {",
                        '  "screens/generated/Orders": () => import("../../../generated/frontend/src/screens/Orders"),',
                        '  "screens/generated/reports/Detail": () => import("../../../generated/frontend/src/screens/reports/Detail"),',
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            report = smoke_preview_host(
                generated_screens_dir=generated_dir,
                preview_host_dir=preview_host_dir,
            )

            self.assertEqual(report.manifest_screen_count, 3)
            self.assertEqual(report.generated_screen_count, 2)
            self.assertEqual(
                report.route_paths,
                ["/preview/orders", "/preview/reports-Detail"],
            )
            self.assertEqual(report.unresolved_module_count, 0)
            self.assertEqual(report.warnings, [])
            self.assertEqual(len(report.screens), 2)
            self.assertTrue(report.screens[0]["route_resolvable"])
            self.assertTrue(report.screens[1]["route_resolvable"])

    def test_smoke_preview_host_detects_unresolved_generated_modules(self) -> None:
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
            (preview_host_dir / "src" / "screens").mkdir(parents=True, exist_ok=True)

            (generated_dir / "Orders.tsx").write_text(
                "export default function Orders() { return null; }\n",
                encoding="utf-8",
            )

            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "./screens.manifest.schema.json",
                        "schemaVersion": "1.0",
                        "generatedAtUtc": "2026-02-12T00:00:00Z",
                        "screens": [
                            {
                                "screenId": "orders",
                                "entryModule": "screens/generated/Orders",
                                "sourceXmlPath": "generated/frontend/src/screens/Orders.tsx",
                                "sourceNodePath": "/generated/screens/orders",
                            },
                            {
                                "screenId": "missing",
                                "entryModule": "screens/generated/Missing",
                                "sourceXmlPath": "generated/frontend/src/screens/Missing.tsx",
                                "sourceNodePath": "/generated/screens/missing",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            registry_generated_path.write_text(
                "\n".join(
                    [
                        "/* Auto-generated */",
                        'import type { ScreenModuleLoader } from "../manifest/types";',
                        "",
                        "export const generatedScreenModuleLoaders: Record<string, ScreenModuleLoader> = {",
                        '  "screens/generated/Orders": () => import("../../../generated/frontend/src/screens/Orders"),',
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            report = smoke_preview_host(
                generated_screens_dir=generated_dir,
                preview_host_dir=preview_host_dir,
            )

            self.assertEqual(report.generated_screen_count, 2)
            self.assertEqual(report.unresolved_module_count, 1)
            self.assertIn(
                "Unresolved generated screen modules detected: 1",
                report.warnings,
            )
            unresolved = next(item for item in report.screens if item["screen_id"] == "missing")
            self.assertFalse(unresolved["route_resolvable"])
            self.assertEqual(
                unresolved["unresolved_reasons"],
                ["missing_registry_loader", "missing_module_file"],
            )


if __name__ == "__main__":
    unittest.main()
