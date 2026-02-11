from __future__ import annotations

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.models import ParseConfig  # noqa: E402
from migrator.parser import parse_xml_file  # noqa: E402
from migrator.validator import compute_roundtrip_structural_diff  # noqa: E402


FIXTURE = Path(__file__).parent / "fixtures" / "simple_screen.xml"


class TestValidator(unittest.TestCase):
    def test_roundtrip_diff_zero_for_fresh_parse(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=False))
        xml_root = ET.parse(FIXTURE).getroot()
        diff = compute_roundtrip_structural_diff(
            xml_root, report.screen.root, include_text=False
        )
        self.assertEqual(diff, 0)

    def test_roundtrip_diff_detects_mutated_ast(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=False))
        report.screen.root.children[0].tag = "DatasetBroken"
        xml_root = ET.parse(FIXTURE).getroot()
        diff = compute_roundtrip_structural_diff(
            xml_root, report.screen.root, include_text=False
        )
        self.assertGreater(diff, 0)


if __name__ == "__main__":
    unittest.main()

