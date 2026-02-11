from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.models import AstNode, EventIR, ScreenIR, SourceRef  # noqa: E402
from migrator.parser import parse_xml_file  # noqa: E402
from migrator.ui_codegen import generate_ui_codegen_artifacts  # noqa: E402


FIXTURE_XML = Path(__file__).parent / "fixtures" / "simple_screen_fixture.txt"
WIDGET_FIXTURE_XML = Path(__file__).parent / "fixtures" / "widget_mapping_fixture.txt"
LAYOUT_STYLE_FIXTURE_XML = Path(__file__).parent / "fixtures" / "layout_style_fixture.txt"


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
            store_path = out_dir / "src" / "behavior" / "simple-screen-fixture.store.ts"
            actions_path = out_dir / "src" / "behavior" / "simple-screen-fixture.actions.ts"

            self.assertEqual(Path(report.tsx_file), tsx_path.resolve())
            self.assertEqual(Path(report.behavior_store_file), store_path.resolve())
            self.assertEqual(Path(report.behavior_actions_file), actions_path.resolve())
            self.assertTrue(tsx_path.exists())
            self.assertTrue(store_path.exists())
            self.assertTrue(actions_path.exists())
            self.assertEqual(report.component_name, "SimpleScreenFixtureScreen")
            self.assertEqual(
                report.wiring_contract.behavior_store_hook_name,
                "useSimpleScreenFixtureBehaviorStore",
            )
            self.assertGreater(report.summary.total_nodes, 0)
            self.assertEqual(report.summary.total_nodes, report.summary.rendered_nodes)
            self.assertEqual(report.summary.wired_event_bindings, 1)

            tsx_text = tsx_path.read_text(encoding="utf-8")
            self.assertIn("export default function SimpleScreenFixtureScreen", tsx_text)
            self.assertIn('from "@mui/material"', tsx_text)
            self.assertIn(
                'import { useSimpleScreenFixtureBehaviorStore } from "../behavior/simple-screen-fixture.store";',
                tsx_text,
            )
            self.assertIn("const behaviorStore = useSimpleScreenFixtureBehaviorStore();", tsx_text)
            self.assertIn('className="mi-generated-screen"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-button"', tsx_text)
            self.assertIn('data-mi-widget={"button"}', tsx_text)
            self.assertIn('onClick={behaviorStore.onFnSearch}', tsx_text)
            self.assertIn(
                'data-mi-source-node={"/Screen[1]/Contents[1]/Button[1]"}',
                tsx_text,
            )
            self.assertIn('data-mi-action-onclick={"onFnSearch"}', tsx_text)
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

    def test_generate_ui_codegen_artifacts_maps_core_widgets_and_fallback(self) -> None:
        parsed = parse_xml_file(WIDGET_FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(WIDGET_FIXTURE_XML),
                out_dir=out_dir,
            )

            tsx_path = Path(report.tsx_file)
            tsx_text = tsx_path.read_text(encoding="utf-8")
            self.assertIn('className="mi-widget mi-widget-static"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-edit"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-combo"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-button"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-grid"', tsx_text)
            self.assertIn('data-mi-widget={"container"}', tsx_text)
            self.assertIn('className="mi-widget mi-widget-fallback"', tsx_text)
            self.assertIn('data-mi-fallback={"unsupported-tag"}', tsx_text)
            self.assertIn(
                (
                    "Unsupported widget tag 'UnknownWidget' at "
                    "/Screen[1]/Contents[1]/Container[1]/UnknownWidget[1]; "
                    "rendered as fallback widget."
                ),
                report.warnings,
            )

    def test_generate_ui_codegen_artifacts_maps_layout_and_style_attributes(self) -> None:
        parsed = parse_xml_file(LAYOUT_STYLE_FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(LAYOUT_STYLE_FIXTURE_XML),
                out_dir=out_dir,
            )

            tsx_path = Path(report.tsx_file)
            tsx_text = tsx_path.read_text(encoding="utf-8")

            self.assertIn(
                'style={{"backgroundColor": "#f5f7fa", "height": "768px", "position": "relative", "width": "1024px"}}',
                tsx_text,
            )
            self.assertIn('className="mi-widget-shell mi-widget-shell-contents"', tsx_text)
            self.assertIn(
                'data-mi-source-node={"/Screen[1]/Contents[1]"}',
                tsx_text,
            )
            self.assertIn('style={{"position": "relative"}}', tsx_text)
            self.assertIn(
                (
                    'style={{"background": "#ffffff", "borderColor": "#d0d7e2", '
                    '"borderRadius": "8px", "borderStyle": "solid", "borderWidth": "1px", '
                    '"bottom": "16px", "left": "24px", "padding": "12px", '
                    '"position": "absolute", "right": "24px", "top": "16px"}}'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    'style={{"color": "#1f2a44", "fontSize": "14px", "fontWeight": "600", '
                    '"height": "32px", "left": "12px", "position": "absolute", '
                    '"textAlign": "center", "top": "12px", "width": "260px"}}'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    'style={{"height": "32px", "left": "12px", "pointerEvents": "none", '
                    '"position": "absolute", "top": "56px", "width": "240px"}}'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    'style={{"display": "none", "height": "32px", "left": "264px", '
                    '"position": "absolute", "top": "56px", "width": "104px"}}'
                ),
                tsx_text,
            )
            self.assertEqual(
                tsx_text.count('style={{"height": "100%", "width": "100%"}}'),
                5,
            )
            self.assertIn(
                (
                    '<TextField className="mi-widget mi-widget-edit" fullWidth size="small" '
                    'label={"Keyword"} style={{"height": "100%", "width": "100%"}} '
                    'defaultValue={"A-100"} />'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    '<FormControl className="mi-widget mi-widget-combo" fullWidth '
                    'size="small" style={{"height": "100%", "width": "100%"}}>'
                ),
                tsx_text,
            )
            self.assertIn(
                'className="mi-widget mi-widget-grid" style={{"height": "100%", "width": "100%"}}',
                tsx_text,
            )

    def test_generate_ui_codegen_artifacts_wires_duplicate_safe_event_actions(self) -> None:
        screen = ScreenIR(
            screen_id="Duplicate Wiring",
            root=AstNode(
                tag="Screen",
                attributes={"id": "DuplicateWiring"},
                text=None,
                source=SourceRef(file_path="dup.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Contents",
                        attributes={},
                        text=None,
                        source=SourceRef(
                            file_path="dup.xml",
                            node_path="/Screen[1]/Contents[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Button",
                                attributes={"id": "btnSave", "text": "Save", "onclick": "fnSave"},
                                text=None,
                                source=SourceRef(
                                    file_path="dup.xml",
                                    node_path="/Screen[1]/Contents[1]/Button[1]",
                                    line=3,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="Button",
                                attributes={"id": "btnSave2", "text": "Save2", "onclick": "fnSave();"},
                                text=None,
                                source=SourceRef(
                                    file_path="dup.xml",
                                    node_path="/Screen[1]/Contents[1]/Button[2]",
                                    line=4,
                                ),
                                children=[],
                            ),
                        ],
                    )
                ],
            ),
            events=[
                EventIR(
                    node_tag="Button",
                    node_id="btnSave",
                    event_name="onclick",
                    handler="fnSave",
                    source=SourceRef(
                        file_path="dup.xml",
                        node_path="/Screen[1]/Contents[1]/Button[1]",
                        line=3,
                    ),
                ),
                EventIR(
                    node_tag="Button",
                    node_id="btnSave2",
                    event_name="onclick",
                    handler="fnSave();",
                    source=SourceRef(
                        file_path="dup.xml",
                        node_path="/Screen[1]/Contents[1]/Button[2]",
                        line=4,
                    ),
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="dup.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn('onClick={behaviorStore.onFnSave}', tsx_text)
            self.assertIn('onClick={behaviorStore.onFnSave2}', tsx_text)
            self.assertIn('data-mi-action-onclick={"onFnSave"}', tsx_text)
            self.assertIn('data-mi-action-onclick={"onFnSave2"}', tsx_text)
            self.assertEqual(report.summary.wired_event_bindings, 2)


if __name__ == "__main__":
    unittest.main()
