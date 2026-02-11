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
            broken_file = str((input_dir / "broken.xml").resolve())
            self.assertEqual(payload["total_xml_files"], 2)
            self.assertEqual(payload["reports_written"], 1)
            self.assertEqual(len(payload["failures"]), 1)
            self.assertIn("gate_pass_fail_counts", payload)
            self.assertIn("failure_reason_counts", payload)
            self.assertIn("failure_file_counts", payload)
            self.assertIn("failure_file_leaderboard", payload)
            self.assertEqual(payload["failure_reason_counts"]["xml_parse_failure"], 1)
            self.assertEqual(payload["gate_pass_fail_counts"]["unknown_tag_count"]["pass_count"], 1)
            self.assertEqual(payload["gate_pass_fail_counts"]["unknown_tag_count"]["fail_count"], 0)
            self.assertEqual(payload["failure_file_counts"][broken_file], 1)
            self.assertTrue((out_dir / "good.json").exists())

    def test_batch_parse_aggregates_gate_failures_and_leaderboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "input"
            out_dir = Path(tmp_dir) / "reports"
            summary_out = Path(tmp_dir) / "summary.json"
            input_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(FIXTURE_XML, input_dir / "good.xml")
            (input_dir / "strict_fail.xml").write_text(
                "<Screen><UnknownWidget /></Screen>",
                encoding="utf-8",
            )
            (input_dir / "broken.xml").write_text("<Screen><Broken>", encoding="utf-8")

            rc = main(
                [
                    "batch-parse",
                    str(input_dir),
                    "--out-dir",
                    str(out_dir),
                    "--summary-out",
                    str(summary_out),
                    "--strict",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            payload = json.loads(summary_out.read_text(encoding="utf-8"))
            strict_fail_file = str((input_dir / "strict_fail.xml").resolve())
            broken_file = str((input_dir / "broken.xml").resolve())
            self.assertEqual(payload["total_xml_files"], 3)
            self.assertEqual(payload["reports_written"], 1)
            self.assertEqual(len(payload["failures"]), 2)
            self.assertEqual(payload["failure_reason_counts"]["strict_gate_failure"], 1)
            self.assertEqual(payload["failure_reason_counts"]["xml_parse_failure"], 1)

            unknown_tag_gate = payload["gate_pass_fail_counts"]["unknown_tag_count"]
            self.assertEqual(unknown_tag_gate["pass_count"], 1)
            self.assertEqual(unknown_tag_gate["fail_count"], 1)

            strict_failure = next(
                item
                for item in payload["failures"]
                if item["file"] == strict_fail_file
            )
            self.assertIn("unknown_tag_count", strict_failure["failed_gates"])

            leaderboard = payload["failure_file_leaderboard"]
            self.assertGreaterEqual(len(leaderboard), 2)
            self.assertEqual(leaderboard[0]["file"], strict_fail_file)
            self.assertGreaterEqual(leaderboard[0]["failed_gate_count"], 1)
            self.assertIn("strict_gate_failure", leaderboard[0]["failure_reasons"])

            broken_entry = next(
                item
                for item in leaderboard
                if item["file"] == broken_file
            )
            self.assertEqual(broken_entry["failed_gate_count"], 0)
            self.assertIn("xml_parse_failure", broken_entry["failure_reasons"])
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
