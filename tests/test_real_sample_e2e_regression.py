from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_real_sample_e2e_regression import main as run_real_sample_e2e_regression_main  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"


class TestRealSampleE2eRegression(unittest.TestCase):
    def test_regression_summary_aggregates_stage_and_risk_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            samples_dir = workspace / "samples"
            out_dir = workspace / "out"
            samples_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(FIXTURE_XML, samples_dir / "good.xml")
            (samples_dir / "map_fail.xml").write_text(
                "<Screen id='Broken'><Transaction id='tx1' serviceid='SVC_TX1' method='POST' /></Screen>",
                encoding="utf-8",
            )
            (samples_dir / "broken.xml").write_text(
                "<Screen><Broken>",
                encoding="utf-8",
            )

            rc = run_real_sample_e2e_regression_main(
                [
                    "--samples-dir",
                    str(samples_dir),
                    "--out-dir",
                    str(out_dir),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            summary_path = out_dir / "regression-summary.json"
            markdown_path = out_dir / "regression-summary.md"
            self.assertTrue(summary_path.exists())
            self.assertTrue(markdown_path.exists())

            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["overall_status"], "failure")
            self.assertEqual(payload["overall_exit_code"], 2)
            self.assertEqual(payload["totals"]["total_samples"], 3)
            self.assertEqual(payload["totals"]["success_count"], 1)
            self.assertEqual(payload["totals"]["failure_count"], 2)
            self.assertEqual(payload["stage_status_counts"]["parse"]["failure"], 1)
            self.assertEqual(payload["stage_status_counts"]["map_api"]["failure"], 1)
            self.assertEqual(payload["risk_trends"]["mapping"]["mapped_failure_total"], 1)
            self.assertEqual(payload["risk_trends"]["mapping"]["files_with_risk"], 1)

            blockers = payload["malformed_xml_blockers"]
            self.assertEqual(len(blockers), 1)
            self.assertTrue(blockers[0]["xml_path"].endswith("broken.xml"))
            self.assertIn("XML parse failure:", blockers[0]["error"])

            top_warning_messages = {item["message"] for item in payload["top_warnings"]}
            self.assertIn("map_api: Mapping failures: 1", top_warning_messages)
            artifacts = payload["artifacts"]
            self.assertTrue(Path(artifacts["all_generated_screens_dir"]).exists())
            self.assertTrue(Path(artifacts["all_generated_behavior_dir"]).exists())
            self.assertGreaterEqual(payload["aggregated_generated"]["screen_file_count"], 1)

    def test_sample_list_file_mode_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            samples_dir = workspace / "samples"
            out_dir = workspace / "out"
            sample_list_file = workspace / "sample-list.txt"
            samples_dir.mkdir(parents=True, exist_ok=True)

            sample_file = samples_dir / "good.xml"
            shutil.copy2(FIXTURE_XML, sample_file)
            sample_list_file.write_text(
                "# agreed sample set\nsamples/good.xml\n",
                encoding="utf-8",
            )

            rc = run_real_sample_e2e_regression_main(
                [
                    "--sample-list-file",
                    str(sample_list_file),
                    "--out-dir",
                    str(out_dir),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            summary_path = out_dir / "regression-summary.json"
            payload = json.loads(summary_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["overall_status"], "success")
            self.assertEqual(payload["overall_exit_code"], 0)
            self.assertEqual(payload["totals"]["total_samples"], 1)
            self.assertEqual(payload["totals"]["success_count"], 1)
            self.assertEqual(payload["totals"]["failure_count"], 0)
            self.assertEqual(payload["stage_status_counts"]["parse"]["success"], 1)
            self.assertEqual(payload["malformed_xml_blockers"], [])
            self.assertEqual(payload["samples"][0]["xml_path"], str(sample_file.resolve()))
            self.assertEqual(payload["aggregated_generated"]["screen_file_count"], 1)
            self.assertEqual(payload["aggregated_generated"]["behavior_file_count"], 2)


if __name__ == "__main__":
    unittest.main()
