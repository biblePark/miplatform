from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.models import AstNode, ScreenIR, SourceRef  # noqa: E402
from migrator.parser import parse_xml_file  # noqa: E402
from migrator.ui_codegen import generate_ui_codegen_artifacts  # noqa: E402


FIXTURE_XML = Path(__file__).parent / "fixtures" / "simple_screen_fixture.txt"


class TestUiCodegen(unittest.TestCase):
    def test_generate_ui_codegen_artifacts_writes_deterministic_tsx(self) -> None:
        parsed = parse_xml_file(FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir,
            )

            tsx_path = out_dir / "src" / "screens" / "simple-screen-fixture.tsx"
            self.assertEqual(Path(report.tsx_file), tsx_path.resolve())
            self.assertTrue(tsx_path.exists())
            self.assertEqual(report.component_name, "SimpleScreenFixtureScreen")
            self.assertGreater(report.summary.total_nodes, 0)
            self.assertEqual(report.summary.total_nodes, report.summary.rendered_nodes)

            tsx_text = tsx_path.read_text(encoding="utf-8")
            self.assertIn("export default function SimpleScreenFixtureScreen", tsx_text)
            self.assertIn('className="mi-generated-screen"', tsx_text)
            self.assertIn('className="mi-node mi-node-button"', tsx_text)
            self.assertIn(
                'data-mi-source-node={"/Screen[1]/Contents[1]/Button[1]"}',
                tsx_text,
            )
            self.assertIn("node=/Screen[1]/Contents[1]/Button[1]", tsx_text)

    def test_generate_ui_codegen_artifacts_warns_for_minimal_screen(self) -> None:
        screen = ScreenIR(
            screen_id="Order Main 2026",
            root=AstNode(
                tag="Screen",
                attributes={"id": "OrderMain"},
                text=None,
                source=SourceRef(file_path="minimal.xml", node_path="/Screen[1]", line=5),
                children=[],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="minimal.xml",
                out_dir=out_dir,
            )

            tsx_path = out_dir / "src" / "screens" / "order-main-2026.tsx"
            self.assertTrue(tsx_path.exists())
            self.assertEqual(Path(report.tsx_file), tsx_path.resolve())
            self.assertEqual(report.component_name, "OrderMain2026Screen")
            self.assertEqual(
                report.warnings,
                ["Screen has no child nodes; generated output is minimal."],
            )

            tsx_text = tsx_path.read_text(encoding="utf-8")
            self.assertIn("sourceXmlPath: minimal.xml", tsx_text)
            self.assertIn("node=/Screen[1] line=5", tsx_text)


if __name__ == "__main__":
    unittest.main()
