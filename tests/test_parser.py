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
        report = parse_xml_file(FIXTURE, config=ParseConfig(strict=False, capture_text=True))

        self.assertEqual(report.screen.screen_id, "simple_screen")
        self.assertEqual(report.stats.total_nodes, 11)
        self.assertEqual(report.stats.tag_counts["Screen"], 1)
        self.assertEqual(report.stats.tag_counts["Dataset"], 1)
        self.assertEqual(report.stats.tag_counts["Contents"], 1)
        self.assertEqual(report.stats.tag_counts["Transaction"], 1)
        self.assertEqual(report.stats.tag_counts["Script"], 1)
        self.assertEqual(report.stats.max_depth, 4)
        self.assertEqual(report.stats.unknown_tags, [])

        root = report.screen.root
        self.assertEqual(root.source.node_path, "/Screen[1]")
        self.assertEqual(root.children[0].source.node_path, "/Screen[1]/Dataset[1]")
        self.assertEqual(root.children[1].source.node_path, "/Screen[1]/Contents[1]")

        self.assertEqual(len(report.screen.datasets), 1)
        self.assertEqual(report.screen.datasets[0].dataset_id, "dsOrder")
        self.assertEqual(len(report.screen.datasets[0].columns), 2)
        self.assertEqual(len(report.screen.datasets[0].records), 1)

        self.assertEqual(len(report.screen.bindings), 1)
        self.assertEqual(report.screen.bindings[0].binding_key, "binddataset")
        self.assertEqual(report.screen.bindings[0].binding_value, "dsOrder")

        self.assertEqual(len(report.screen.events), 1)
        self.assertEqual(report.screen.events[0].event_name, "onclick")
        self.assertEqual(report.screen.events[0].handler, "fnSearch")

        self.assertEqual(len(report.screen.transactions), 1)
        self.assertEqual(report.screen.transactions[0].transaction_id, "SVC_ORDER_SEARCH")
        self.assertEqual(report.screen.transactions[0].endpoint, "/api/orders/search")
        self.assertEqual(report.screen.transactions[0].method, "POST")

        self.assertEqual(len(report.screen.scripts), 1)
        self.assertEqual(report.screen.scripts[0].script_name, "fnSearch")
        self.assertIn("transaction('searchOrders')", report.screen.scripts[0].body)

        self.assertTrue(report.stats.canonical_source_hash)
        self.assertTrue(report.stats.canonical_ast_hash)
        self.assertEqual(report.stats.roundtrip_mismatches, [])

        gate_map = {gate.name: gate for gate in report.gates}
        self.assertTrue(gate_map["roundtrip_structural_diff"].passed)
        self.assertTrue(gate_map["canonical_roundtrip_hash_match"].passed)
        self.assertTrue(gate_map["dataset_extraction_coverage"].passed)
        self.assertTrue(gate_map["binding_extraction_coverage"].passed)
        self.assertTrue(gate_map["event_extraction_coverage"].passed)
        self.assertTrue(gate_map["transaction_extraction_coverage"].passed)
        self.assertTrue(gate_map["script_extraction_coverage"].passed)

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
                "Transaction",
                "Script",
            },
            known_attrs_by_tag={
                "Screen": {"id"},
                "Dataset": {"id"},
                "Button": {"id", "text"},
                "Grid": {"id", "binddataset"},
                "Transaction": {"id"},
                "Script": {"name"},
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
            capture_text=True,
        )
        report = parse_xml_file(FIXTURE, config=config)

        self.assertEqual(len(report.stats.unknown_tags), 0)
        self.assertEqual(len(report.stats.unknown_attrs), 0)
        self.assertTrue(all(gate.passed for gate in report.gates))


if __name__ == "__main__":
    unittest.main()
