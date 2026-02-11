from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.cli import main  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen.xml"
KNOWN_TAGS = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS = FIXTURES_DIR / "known_attrs_all.json"


class TestCli(unittest.TestCase):
    def test_parse_command_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "report.json"
            rc = main(
                [
                    "parse",
                    str(FIXTURE_XML),
                    "--out",
                    str(out_file),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out_file.exists())

            payload = json.loads(out_file.read_text(encoding="utf-8"))
            gate_names = {gate["name"] for gate in payload["gates"]}
            self.assertIn("canonical_roundtrip_hash_match", gate_names)
            self.assertIn("transaction_extraction_coverage", gate_names)
            self.assertIn("script_extraction_coverage", gate_names)

    def test_batch_parse_reports_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "input"
            out_dir = Path(tmp_dir) / "reports"
            summary_out = Path(tmp_dir) / "summary.json"
            input_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(FIXTURE_XML, input_dir / "good.xml")
            (input_dir / "broken.xml").write_text("<Screen><Broken>", encoding="utf-8")

            rc = main(
                [
                    "batch-parse",
                    str(input_dir),
                    "--out-dir",
                    str(out_dir),
                    "--summary-out",
                    str(summary_out),
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            self.assertTrue(summary_out.exists())
            payload = json.loads(summary_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_xml_files"], 2)
            self.assertEqual(payload["reports_written"], 1)
            self.assertEqual(len(payload["failures"]), 1)
            self.assertTrue((out_dir / "good.json").exists())

    def test_map_api_generates_route_service_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-api"
            report_out = Path(tmp_dir) / "mapping-report.json"
            rc = main(
                [
                    "map-api",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue(report_out.exists())
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_transactions"], 1)
            self.assertEqual(payload["summary"]["mapped_success"], 1)
            self.assertEqual(payload["summary"]["mapped_failure"], 0)
            self.assertEqual(payload["summary"]["unsupported"], 0)
            self.assertEqual(payload["results"][0]["status"], "success")

            route_file = out_dir / "src" / "routes" / "simple-screen.routes.js"
            service_file = out_dir / "src" / "services" / "simple-screen.service.js"
            self.assertTrue(route_file.exists())
            self.assertTrue(service_file.exists())
            self.assertIn(
                'router.post("/api/orders/search"',
                route_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "async function svcOrderSearch(req)",
                service_file.read_text(encoding="utf-8"),
            )

    def test_map_api_returns_failure_when_mapping_has_missing_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "broken.xml"
            xml_path.write_text(
                "<Screen id='Broken'><Transaction id='tx1' serviceid='SVC_TX1' method='POST' /></Screen>",
                encoding="utf-8",
            )
            out_dir = Path(tmp_dir) / "generated-api"
            report_out = Path(tmp_dir) / "mapping-report.json"

            rc = main(
                [
                    "map-api",
                    str(xml_path),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_transactions"], 1)
            self.assertEqual(payload["summary"]["mapped_success"], 0)
            self.assertEqual(payload["summary"]["mapped_failure"], 1)
            self.assertEqual(payload["summary"]["unsupported"], 0)
            self.assertEqual(payload["results"][0]["reason"], "missing_endpoint")


if __name__ == "__main__":
    unittest.main()
