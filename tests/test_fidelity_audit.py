from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.fidelity_audit import generate_fidelity_audit_report  # noqa: E402
from migrator.models import ParseConfig  # noqa: E402
from migrator.parser import parse_xml_file  # noqa: E402
from migrator.ui_codegen import generate_ui_codegen_artifacts  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"


class TestFidelityAudit(unittest.TestCase):
    def test_audit_passes_for_generated_ui_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parse_report = parse_xml_file(
                FIXTURE_XML,
                config=ParseConfig(capture_text=True),
            )
            ui_report = generate_ui_codegen_artifacts(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=Path(tmp_dir) / "generated-ui",
            )

            fidelity_report = generate_fidelity_audit_report(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                generated_ui_file=ui_report.tsx_file,
            )

            self.assertFalse(fidelity_report.has_blocking_risks())
            self.assertEqual(fidelity_report.summary.missing_node_count, 0)
            self.assertEqual(fidelity_report.summary.position_style_nodes_with_risk, 0)
            self.assertGreater(fidelity_report.summary.position_attribute_total, 0)
            self.assertGreater(fidelity_report.summary.style_attribute_total, 0)
            self.assertEqual(
                fidelity_report.summary.position_attribute_total,
                fidelity_report.summary.position_attribute_covered,
            )
            self.assertEqual(
                fidelity_report.summary.style_attribute_total,
                fidelity_report.summary.style_attribute_covered,
            )

    def test_audit_detects_missing_node_and_style_coverage_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parse_report = parse_xml_file(
                FIXTURE_XML,
                config=ParseConfig(capture_text=True),
            )
            ui_report = generate_ui_codegen_artifacts(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=Path(tmp_dir) / "generated-ui",
            )
            tsx_path = Path(ui_report.tsx_file)
            text = tsx_path.read_text(encoding="utf-8")

            tampered = text.replace(
                'data-mi-source-node={"/Screen[1]/Contents[1]/Grid[1]"}',
                'data-mi-source-node={"__tampered__/Grid[1]"}',
                1,
            )
            tampered = re.sub(r',\s*"left":\s*"24px"', "", tampered, count=1)
            self.assertNotEqual(text, tampered)
            tsx_path.write_text(tampered, encoding="utf-8")

            fidelity_report = generate_fidelity_audit_report(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                generated_ui_file=tsx_path,
            )

            self.assertTrue(fidelity_report.has_blocking_risks())
            self.assertIn(
                "/Screen[1]/Contents[1]/Grid[1]",
                fidelity_report.missing_node_paths,
            )
            self.assertGreater(
                fidelity_report.summary.position_style_nodes_with_risk,
                0,
            )
            self.assertGreater(len(fidelity_report.position_style_coverage_risks), 0)

    def test_report_serialization_is_deterministic_without_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parse_report = parse_xml_file(
                FIXTURE_XML,
                config=ParseConfig(capture_text=True),
            )
            ui_report = generate_ui_codegen_artifacts(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=Path(tmp_dir) / "generated-ui",
            )

            report_a = generate_fidelity_audit_report(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                generated_ui_file=ui_report.tsx_file,
            )
            report_b = generate_fidelity_audit_report(
                screen=parse_report.screen,
                input_xml_path=str(FIXTURE_XML),
                generated_ui_file=ui_report.tsx_file,
            )

            payload_a = report_a.to_dict(include_generated_at=False)
            payload_b = report_b.to_dict(include_generated_at=False)

            self.assertEqual(payload_a, payload_b)
            self.assertEqual(
                json.dumps(payload_a, sort_keys=True, ensure_ascii=False),
                json.dumps(payload_b, sort_keys=True, ensure_ascii=False),
            )


if __name__ == "__main__":
    unittest.main()
