from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from real_sample_baseline import main as real_sample_baseline_main  # noqa: E402


STAGES = ("parse", "map_api", "gen_ui", "fidelity_audit", "sync_preview")


class TestRealSampleBaseline(unittest.TestCase):
    def _build_summary(
        self,
        *,
        total_samples: int = 3,
        success_count: int = 2,
        failure_count: int = 1,
        stage_failures: dict[str, int] | None = None,
        extraction_files_with_risk: int = 1,
        extraction_gate_count: int = 1,
        mapping_files_with_risk: int = 1,
        mapping_mapped_failure_total: int = 1,
        mapping_unsupported_total: int = 2,
        fidelity_files_with_risk: int = 1,
        fidelity_gate_count: int = 1,
        fidelity_ui_fallback_warning_total: int = 2,
        fidelity_missing_node_total: int = 3,
        fidelity_position_style_nodes_with_risk_total: int = 4,
        malformed_blocker_count: int = 1,
    ) -> dict[str, object]:
        stage_failures = stage_failures or {}
        stage_status_counts: dict[str, dict[str, int]] = {}
        for stage in STAGES:
            failure = int(stage_failures.get(stage, 0))
            success = max(0, total_samples - failure)
            stage_status_counts[stage] = {
                "success": success,
                "failure": failure,
            }

        blockers = [
            {
                "xml_path": f"/tmp/blocker-{index}.xml",
                "error": "XML parse failure: malformed",
            }
            for index in range(malformed_blocker_count)
        ]

        samples = [
            {"xml_path": f"/tmp/sample-{index:03d}.xml"}
            for index in range(1, total_samples + 1)
        ]

        return {
            "totals": {
                "total_samples": total_samples,
                "success_count": success_count,
                "failure_count": failure_count,
            },
            "stage_status_counts": stage_status_counts,
            "risk_trends": {
                "extraction": {
                    "files_with_risk": extraction_files_with_risk,
                    "gate_failure_counts": {
                        "dataset_extraction_coverage": extraction_gate_count,
                    },
                },
                "mapping": {
                    "files_with_risk": mapping_files_with_risk,
                    "mapped_failure_total": mapping_mapped_failure_total,
                    "unsupported_total": mapping_unsupported_total,
                },
                "fidelity": {
                    "files_with_risk": fidelity_files_with_risk,
                    "gate_failure_counts": {
                        "unknown_tag_count": fidelity_gate_count,
                    },
                    "ui_fallback_warning_total": fidelity_ui_fallback_warning_total,
                    "missing_node_total": fidelity_missing_node_total,
                    "position_style_nodes_with_risk_total": (
                        fidelity_position_style_nodes_with_risk_total
                    ),
                },
            },
            "malformed_xml_blockers": blockers,
            "samples": samples,
        }

    def test_snapshot_persists_round_baseline_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            summary_path = workspace / "out" / "regression-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_payload = self._build_summary()
            summary_path.write_text(
                json.dumps(summary_payload, indent=2),
                encoding="utf-8",
            )

            rc = real_sample_baseline_main(
                [
                    "snapshot",
                    "--summary-json",
                    str(summary_path),
                    "--round",
                    "R10",
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            snapshot_json = summary_path.parent / "baselines" / "R10" / "baseline-summary.json"
            snapshot_md = summary_path.parent / "baselines" / "R10" / "baseline-summary.md"

            self.assertTrue(snapshot_json.exists())
            self.assertTrue(snapshot_md.exists())

            snapshot_payload = json.loads(snapshot_json.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_payload["round_id"], "R10")
            self.assertEqual(snapshot_payload["metrics"]["stage.parse.failure"], 0)
            self.assertEqual(snapshot_payload["metrics"]["risk.mapping.mapped_failure_total"], 1)
            self.assertEqual(snapshot_payload["sample_set"]["count"], 3)

    def test_diff_reports_stage_and_risk_regressions_and_improvements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            baseline_summary = workspace / "baseline" / "regression-summary.json"
            current_summary = workspace / "current" / "regression-summary.json"
            baseline_summary.parent.mkdir(parents=True, exist_ok=True)
            current_summary.parent.mkdir(parents=True, exist_ok=True)

            baseline_payload = self._build_summary(
                stage_failures={"parse": 0, "map_api": 1},
                mapping_mapped_failure_total=2,
                mapping_unsupported_total=2,
                fidelity_missing_node_total=1,
            )
            current_payload = self._build_summary(
                stage_failures={"parse": 1, "map_api": 0},
                mapping_mapped_failure_total=1,
                mapping_unsupported_total=1,
                fidelity_missing_node_total=3,
            )
            baseline_summary.write_text(
                json.dumps(baseline_payload, indent=2),
                encoding="utf-8",
            )
            current_summary.write_text(
                json.dumps(current_payload, indent=2),
                encoding="utf-8",
            )

            snapshot_rc = real_sample_baseline_main(
                [
                    "snapshot",
                    "--summary-json",
                    str(baseline_summary),
                    "--round",
                    "R09",
                    "--pretty",
                ]
            )
            self.assertEqual(snapshot_rc, 0)

            diff_json = workspace / "diff" / "baseline-diff.json"
            diff_md = workspace / "diff" / "baseline-diff.md"
            diff_rc = real_sample_baseline_main(
                [
                    "diff",
                    "--current-summary-json",
                    str(current_summary),
                    "--baseline-round",
                    "R09",
                    "--baseline-root-dir",
                    str(baseline_summary.parent / "baselines"),
                    "--current-round",
                    "R10",
                    "--diff-json-out",
                    str(diff_json),
                    "--diff-markdown-out",
                    str(diff_md),
                    "--pretty",
                ]
            )
            self.assertEqual(diff_rc, 0)
            self.assertTrue(diff_json.exists())
            self.assertTrue(diff_md.exists())

            payload = json.loads(diff_json.read_text(encoding="utf-8"))
            entries = {item["metric"]: item for item in payload["entries"]}

            self.assertEqual(entries["stage.parse.failure"]["movement"], "regression")
            self.assertEqual(entries["stage.map_api.failure"]["movement"], "improvement")
            self.assertEqual(
                entries["risk.mapping.mapped_failure_total"]["movement"],
                "improvement",
            )
            self.assertEqual(
                entries["risk.fidelity.missing_node_total"]["movement"],
                "regression",
            )
            self.assertGreater(payload["dimension_summary"]["stage"]["regression"], 0)
            self.assertGreater(payload["dimension_summary"]["risk_trend"]["regression"], 0)

            markdown = diff_md.read_text(encoding="utf-8")
            self.assertIn("## Stage KPI Deltas", markdown)
            self.assertIn("## Risk Trend KPI Deltas", markdown)

    def test_diff_strict_fails_when_tolerance_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            baseline_summary = workspace / "baseline" / "regression-summary.json"
            current_summary = workspace / "current" / "regression-summary.json"
            tolerance_file = workspace / "tolerances.json"
            baseline_summary.parent.mkdir(parents=True, exist_ok=True)
            current_summary.parent.mkdir(parents=True, exist_ok=True)

            baseline_summary.write_text(
                json.dumps(self._build_summary(mapping_mapped_failure_total=1), indent=2),
                encoding="utf-8",
            )
            current_summary.write_text(
                json.dumps(self._build_summary(mapping_mapped_failure_total=4), indent=2),
                encoding="utf-8",
            )
            tolerance_file.write_text(
                json.dumps(
                    {
                        "lower_is_better": {
                            "risk.mapping.mapped_failure_total": 1,
                        },
                        "higher_is_better": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            snapshot_rc = real_sample_baseline_main(
                [
                    "snapshot",
                    "--summary-json",
                    str(baseline_summary),
                    "--round",
                    "R09",
                ]
            )
            self.assertEqual(snapshot_rc, 0)

            diff_json = workspace / "diff" / "baseline-diff.json"
            strict_rc = real_sample_baseline_main(
                [
                    "diff",
                    "--current-summary-json",
                    str(current_summary),
                    "--baseline-round",
                    "R09",
                    "--baseline-root-dir",
                    str(baseline_summary.parent / "baselines"),
                    "--diff-json-out",
                    str(diff_json),
                    "--tolerances-file",
                    str(tolerance_file),
                    "--strict",
                ]
            )

            self.assertEqual(strict_rc, 2)
            payload = json.loads(diff_json.read_text(encoding="utf-8"))
            self.assertFalse(payload["tolerance_evaluation"]["passed"])
            violation_metrics = {
                item["metric"] for item in payload["tolerance_evaluation"]["violations"]
            }
            self.assertIn("risk.mapping.mapped_failure_total", violation_metrics)

    def test_diff_strict_passes_when_regression_is_within_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            baseline_summary = workspace / "baseline" / "regression-summary.json"
            current_summary = workspace / "current" / "regression-summary.json"
            tolerance_file = workspace / "tolerances.json"
            baseline_summary.parent.mkdir(parents=True, exist_ok=True)
            current_summary.parent.mkdir(parents=True, exist_ok=True)

            baseline_summary.write_text(
                json.dumps(self._build_summary(mapping_mapped_failure_total=1), indent=2),
                encoding="utf-8",
            )
            current_summary.write_text(
                json.dumps(self._build_summary(mapping_mapped_failure_total=2), indent=2),
                encoding="utf-8",
            )
            tolerance_file.write_text(
                json.dumps(
                    {
                        "lower_is_better": {
                            "risk.mapping.mapped_failure_total": 1,
                        },
                        "higher_is_better": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            snapshot_rc = real_sample_baseline_main(
                [
                    "snapshot",
                    "--summary-json",
                    str(baseline_summary),
                    "--round",
                    "R09",
                ]
            )
            self.assertEqual(snapshot_rc, 0)

            diff_json = workspace / "diff" / "baseline-diff.json"
            strict_rc = real_sample_baseline_main(
                [
                    "diff",
                    "--current-summary-json",
                    str(current_summary),
                    "--baseline-round",
                    "R09",
                    "--baseline-root-dir",
                    str(baseline_summary.parent / "baselines"),
                    "--diff-json-out",
                    str(diff_json),
                    "--tolerances-file",
                    str(tolerance_file),
                    "--strict",
                ]
            )

            self.assertEqual(strict_rc, 0)
            payload = json.loads(diff_json.read_text(encoding="utf-8"))
            self.assertTrue(payload["tolerance_evaluation"]["passed"])
            self.assertEqual(payload["tolerance_evaluation"]["violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
