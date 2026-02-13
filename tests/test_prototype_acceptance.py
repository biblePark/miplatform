from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.prototype_acceptance import (  # noqa: E402
    PrototypeAcceptanceThresholds,
    generate_prototype_acceptance_report,
)


class TestPrototypeAcceptance(unittest.TestCase):
    def _write_summary(
        self,
        *,
        summary_path: Path,
        behavior_actions_file: Path,
        total_transactions: int,
        overall_status: str,
        fidelity_risk: bool,
        missing_node_count: int,
        position_style_nodes_with_risk: int,
        total_event_attributes: int,
        runtime_wired_event_props: int,
        unsupported_event_bindings: int,
    ) -> None:
        payload = {
            "screen_id": summary_path.stem,
            "overall_status": overall_status,
            "stages": {
                "map_api": {
                    "total_transactions": total_transactions,
                },
                "fidelity_audit": {
                    "risk_detected": fidelity_risk,
                    "missing_node_count": missing_node_count,
                    "position_style_nodes_with_risk": position_style_nodes_with_risk,
                },
                "gen_ui": {
                    "total_event_attributes": total_event_attributes,
                    "runtime_wired_event_props": runtime_wired_event_props,
                    "unsupported_event_bindings": unsupported_event_bindings,
                    "behavior_actions_file": str(behavior_actions_file),
                },
            },
        }
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_report_passes_with_clean_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            actions_file = workspace / "screen.actions.ts"
            actions_file.write_text(
                "export function createScreenBehaviorActions() { return {}; }\n",
                encoding="utf-8",
            )
            summary_file = workspace / "clean.migration-summary.json"
            self._write_summary(
                summary_path=summary_file,
                behavior_actions_file=actions_file,
                total_transactions=1,
                overall_status="success",
                fidelity_risk=False,
                missing_node_count=0,
                position_style_nodes_with_risk=0,
                total_event_attributes=2,
                runtime_wired_event_props=2,
                unsupported_event_bindings=0,
            )

            report = generate_prototype_acceptance_report(
                [summary_file],
                thresholds=PrototypeAcceptanceThresholds(),
            )

            self.assertEqual(report.verdict, "pass")
            self.assertEqual(report.totals.total_migration_summaries, 1)
            self.assertEqual(report.totals.total_transactions, 1)
            self.assertEqual(report.totals.failed_migration_count, 0)
            self.assertEqual(report.totals.fidelity_risk_count, 0)
            self.assertEqual(report.totals.unsupported_event_bindings, 0)
            self.assertEqual(report.totals.unresolved_transaction_adapter_signals, 0)
            self.assertEqual(report.warnings, [])
            self.assertTrue(all(item.passed for item in report.kpi_results))

    def test_report_fails_for_fidelity_event_and_adapter_risks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            actions_file = workspace / "screen.actions.ts"
            actions_file.write_text(
                (
                    "const error = { code: \"UNIMPLEMENTED_TRANSACTION_ADAPTER\" };\n"
                    "export default error;\n"
                ),
                encoding="utf-8",
            )
            summary_file = workspace / "risk.migration-summary.json"
            self._write_summary(
                summary_path=summary_file,
                behavior_actions_file=actions_file,
                total_transactions=1,
                overall_status="failure",
                fidelity_risk=True,
                missing_node_count=1,
                position_style_nodes_with_risk=2,
                total_event_attributes=3,
                runtime_wired_event_props=1,
                unsupported_event_bindings=2,
            )

            report = generate_prototype_acceptance_report([summary_file])

            self.assertEqual(report.verdict, "fail")
            self.assertEqual(report.totals.total_transactions, 1)
            self.assertEqual(report.totals.failed_migration_count, 1)
            self.assertEqual(report.totals.fidelity_risk_count, 1)
            self.assertEqual(report.totals.unsupported_event_bindings, 2)
            self.assertEqual(report.totals.unresolved_transaction_adapter_signals, 1)
            self.assertEqual(report.totals.event_runtime_wiring_coverage_ratio, 0.333333)

            failed_kpis = [item.name for item in report.kpi_results if not item.passed]
            self.assertIn("failed_migration_count", failed_kpis)
            self.assertIn("fidelity_risk_count", failed_kpis)
            self.assertIn("event_runtime_wiring_coverage_ratio", failed_kpis)
            self.assertIn("unsupported_event_bindings", failed_kpis)
            self.assertIn("unresolved_transaction_adapter_signals", failed_kpis)

    def test_report_serialization_is_deterministic_without_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            actions_file = workspace / "screen.actions.ts"
            actions_file.write_text(
                "export const token = \"NO_UNRESOLVED_MARKERS\";\n",
                encoding="utf-8",
            )

            summary_b = workspace / "b.migration-summary.json"
            self._write_summary(
                summary_path=summary_b,
                behavior_actions_file=actions_file,
                total_transactions=1,
                overall_status="success",
                fidelity_risk=False,
                missing_node_count=0,
                position_style_nodes_with_risk=0,
                total_event_attributes=1,
                runtime_wired_event_props=1,
                unsupported_event_bindings=0,
            )

            summary_a = workspace / "a.migration-summary.json"
            self._write_summary(
                summary_path=summary_a,
                behavior_actions_file=actions_file,
                total_transactions=1,
                overall_status="success",
                fidelity_risk=False,
                missing_node_count=0,
                position_style_nodes_with_risk=0,
                total_event_attributes=2,
                runtime_wired_event_props=2,
                unsupported_event_bindings=0,
            )

            report_a = generate_prototype_acceptance_report([workspace])
            report_b = generate_prototype_acceptance_report([workspace])
            payload_a = report_a.to_dict(include_generated_at=False)
            payload_b = report_b.to_dict(include_generated_at=False)

            self.assertEqual(payload_a, payload_b)
            self.assertEqual(
                payload_a["summary_files"],
                [
                    str(summary_a.resolve()),
                    str(summary_b.resolve()),
                ],
            )


if __name__ == "__main__":
    unittest.main()
