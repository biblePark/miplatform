from __future__ import annotations

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.models import ParseConfig  # noqa: E402
from migrator.parser import parse_xml_file  # noqa: E402
from migrator.validator import (  # noqa: E402
    compute_canonical_hash_pair,
    compute_roundtrip_mismatches,
    compute_roundtrip_structural_diff,
)


FIXTURE = Path(__file__).parent / "fixtures" / "simple_screen_fixture.txt"


class TestValidator(unittest.TestCase):
    def test_roundtrip_diff_zero_for_fresh_parse(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=True))
        xml_root = ET.parse(FIXTURE).getroot()
        diff = compute_roundtrip_structural_diff(
            xml_root, report.screen.root, include_text=True
        )
        self.assertEqual(diff, 0)

    def test_roundtrip_mismatch_details_include_path(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=False))
        report.screen.root.children[0].tag = "DatasetBroken"
        xml_root = ET.parse(FIXTURE).getroot()

        mismatches = compute_roundtrip_mismatches(
            xml_root, report.screen.root, include_text=False
        )
        self.assertGreater(len(mismatches), 0)
        self.assertEqual(mismatches[0].position_path, "1.1")
        self.assertEqual(mismatches[0].reason, "tag_mismatch")

    def test_canonical_hash_pair_matches_for_fresh_parse(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=True))
        xml_root = ET.parse(FIXTURE).getroot()

        source_hash, ast_hash = compute_canonical_hash_pair(
            xml_root, report.screen.root, include_text=True
        )
        self.assertEqual(source_hash, ast_hash)

    def test_canonical_hash_pair_detects_mutation(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=True))
        report.screen.root.children[2].attributes["url"] = "/api/orders/changed"
        xml_root = ET.parse(FIXTURE).getroot()

        source_hash, ast_hash = compute_canonical_hash_pair(
            xml_root, report.screen.root, include_text=True
        )
        self.assertNotEqual(source_hash, ast_hash)


if __name__ == "__main__":
    unittest.main()
