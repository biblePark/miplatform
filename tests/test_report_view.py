from __future__ import annotations

import contextlib
import json
from io import StringIO
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from migrator.cli import main as migrator_main  # noqa: E402
from report_view import main as report_view_main  # noqa: E402
from run_real_sample_e2e_regression import main as run_real_sample_e2e_regression_main  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"
KNOWN_TAGS = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS = FIXTURES_DIR / "known_attrs_all.json"


class TestReportView(unittest.TestCase):
    def test_view_text_for_migration_summary_and_prototype_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            out_dir = workspace / "out"
            api_out_dir = workspace / "generated-api"
            ui_out_dir = workspace / "generated-ui"
            preview_host_dir = workspace / "preview-host"
            preview_host_dir.mkdir(parents=True, exist_ok=True)

            migrate_rc = migrator_main(
                [
                    "migrate-e2e",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(out_dir),
                    "--api-out-dir",
                    str(api_out_dir),
                    "--ui-out-dir",
                    str(ui_out_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )
            self.assertEqual(migrate_rc, 0)

            migration_summary = out_dir / "simple_screen_fixture.migration-summary.json"
            self.assertTrue(migration_summary.exists())

            prototype_report = workspace / "prototype-acceptance.json"
            prototype_rc = migrator_main(
                [
                    "prototype-accept",
                    str(migration_summary),
                    "--report-out",
                    str(prototype_report),
                    "--max-unresolved-transaction-adapter-signals",
                    "10",
                    "--pretty",
                ]
            )
            self.assertEqual(prototype_rc, 0)

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                view_rc = report_view_main([str(migration_summary), str(prototype_report)])

            self.assertEqual(view_rc, 0)
            rendered = stdout_buffer.getvalue()
            self.assertIn("[migration_summary]", rendered)
            self.assertIn("[prototype_acceptance]", rendered)
            self.assertIn("- overall: success (exit=0)", rendered)
            self.assertIn("- verdict: pass", rendered)
            self.assertEqual(stderr_buffer.getvalue(), "")

    def test_view_json_contract_for_regression_summary_directory_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            samples_dir = workspace / "samples"
            out_dir = workspace / "out"
            samples_dir.mkdir(parents=True, exist_ok=True)

            sample_file = samples_dir / "good.xml"
            shutil.copy2(FIXTURE_XML, sample_file)

            regression_rc = run_real_sample_e2e_regression_main(
                [
                    "--samples-dir",
                    str(samples_dir),
                    "--out-dir",
                    str(out_dir),
                    "--pretty",
                ]
            )
            self.assertEqual(regression_rc, 0)

            # Directory mode scans all nested JSON files; unsupported JSON contracts are skipped.
            (out_dir / "unsupported.json").write_text(
                json.dumps({"kind": "unsupported"}, indent=2),
                encoding="utf-8",
            )

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                view_rc = report_view_main([str(out_dir), "--format", "json", "--pretty"])

            self.assertEqual(view_rc, 0)
            payload = json.loads(stdout_buffer.getvalue())
            self.assertGreaterEqual(payload["report_count"], 2)

            reports = payload["reports"]
            regression_reports = [
                item for item in reports if item["report_type"] == "regression_summary"
            ]
            self.assertEqual(len(regression_reports), 1)
            summary = regression_reports[0]["summary"]
            self.assertEqual(summary["overall_status"], "success")
            self.assertEqual(summary["overall_exit_code"], 0)
            self.assertEqual(summary["total_samples"], 1)
            self.assertEqual(summary["success_count"], 1)
            self.assertEqual(summary["failure_count"], 0)
            self.assertEqual(summary["malformed_xml_blocker_count"], 0)
            self.assertIn("parse", summary["stage_failure_counts"])
            self.assertIn("Skipped unsupported JSON files:", stderr_buffer.getvalue())

    def test_explicit_unknown_report_file_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            unknown_report = Path(tmp_dir) / "unknown.json"
            unknown_report.write_text(
                json.dumps({"unexpected": "payload"}, indent=2),
                encoding="utf-8",
            )

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                rc = report_view_main([str(unknown_report)])

            self.assertEqual(rc, 2)
            self.assertEqual(stdout_buffer.getvalue(), "")
            self.assertIn("Unsupported report contract:", stderr_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
