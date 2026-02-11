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


if __name__ == "__main__":
    unittest.main()
