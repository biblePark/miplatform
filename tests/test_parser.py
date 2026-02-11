from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.models import ParseConfig  # noqa: E402
from migrator.parser import ParseStrictError, parse_xml_file  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES_DIR / "simple_screen.xml"
KNOWN_TAGS_FILE = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS_FILE = FIXTURES_DIR / "known_attrs_all.json"


class TestParser(unittest.TestCase):
    def test_parse_smoke(self) -> None:
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=False))

        self.assertEqual(report.screen.screen_id, "simple_screen")
        self.assertEqual(report.stats.total_nodes, 9)
        self.assertEqual(report.stats.tag_counts["Screen"], 1)
        self.assertEqual(report.stats.tag_counts["Dataset"], 1)
        self.assertEqual(report.stats.tag_counts["Contents"], 1)
        self.assertEqual(report.stats.max_depth, 4)
        self.assertEqual(report.stats.unknown_tags, [])

        root = report.screen.root
        self.assertEqual(root.source.node_path, "/Screen[1]")
        self.assertEqual(root.children[0].source.node_path, "/Screen[1]/Dataset[1]")
        self.assertEqual(root.children[1].source.node_path, "/Screen[1]/Contents[1]")

    def test_strict_unknown_tag_fails(self) -> None:
        config = ParseConfig(
            strict=True,
            known_tags={"Screen", "Dataset", "colinfo", "column", "record", "Contents"},
        )
        with self.assertRaises(ParseStrictError):
            parse_xml_file(FIXTURE, config=config)

    def test_strict_unknown_attr_fails(self) -> None:
        config = ParseConfig(
            strict=True,
            known_tags={
                "Screen",
                "Dataset",
                "colinfo",
                "column",
                "record",
                "Contents",
                "Button",
                "Grid",
            },
            known_attrs_by_tag={
                "Screen": {"id"},
                "Dataset": {"id"},
                "Button": {"id", "text"},
                "Grid": {"id", "binddataset"},
                "*": set(),
            },
        )
        with self.assertRaises(ParseStrictError):
            parse_xml_file(FIXTURE, config=config)

    def test_strict_with_full_profiles_passes(self) -> None:
        known_tags = {
            line.strip()
            for line in KNOWN_TAGS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        known_attrs_raw = json.loads(KNOWN_ATTRS_FILE.read_text(encoding="utf-8"))
        known_attrs = {tag: set(attrs) for tag, attrs in known_attrs_raw.items()}

        config = ParseConfig(
            strict=True,
            known_tags=known_tags,
            known_attrs_by_tag=known_attrs,
        )
        report = parse_xml_file(FIXTURE, config=config)

        self.assertEqual(len(report.stats.unknown_tags), 0)
        self.assertEqual(len(report.stats.unknown_attrs), 0)
        self.assertTrue(all(gate.passed for gate in report.gates))


if __name__ == "__main__":
    unittest.main()
