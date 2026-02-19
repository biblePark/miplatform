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
            self.assertEqual(report.summary.total_event_attributes, 1)
            self.assertEqual(report.summary.runtime_wired_event_props, 1)
            self.assertEqual(report.summary.unsupported_event_bindings, 0)
            self.assertEqual(report.unsupported_event_inventory, [])
            self.assertEqual(report.requested_mode, "mui")
            self.assertEqual(report.mode, "mui")
            self.assertIn("explicit_mui_mode", report.decision_reason)
            self.assertGreaterEqual(report.risk_score, 0.0)
            self.assertEqual(report.auto_risk_threshold, 0.58)
            self.assertEqual(
                set(report.risk_signal_counts),
                {"total_nodes", "positioned_nodes", "fallback_nodes", "tab_nodes", "event_attributes"},
            )
            self.assertEqual(report.risk_signal_counts["total_nodes"], report.summary.total_nodes)
            self.assertEqual(
                set(report.risk_signal_scores),
                {"positioned_nodes", "fallback_nodes", "event_attributes", "tab_nodes", "total"},
            )
            self.assertEqual(report.risk_signal_scores["total"], report.risk_score)

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

    def test_generate_ui_codegen_artifacts_supports_strict_mode_low_level_render(self) -> None:
        parsed = parse_xml_file(FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir,
                mode="strict",
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertEqual(report.requested_mode, "strict")
            self.assertEqual(report.mode, "strict")
            self.assertIn("explicit_strict_mode", report.decision_reason)
            self.assertEqual(report.auto_risk_threshold, 0.58)
            self.assertNotIn('from "@mui/material"', tsx_text)
            self.assertIn('<div className="mi-widget-shell mi-widget-shell-button"', tsx_text)
            self.assertIn('<button className="mi-widget mi-widget-button"', tsx_text)
            self.assertIn('onClick={behaviorStore.onFnSearch}', tsx_text)

    def test_generate_ui_codegen_artifacts_auto_mode_records_risk_decision(self) -> None:
        screen = ScreenIR(
            screen_id="Auto Policy High Risk",
            root=AstNode(
                tag="Screen",
                attributes={"id": "AutoPolicyHighRisk"},
                text=None,
                source=SourceRef(file_path="auto-risk.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Contents",
                        attributes={"left": "0", "top": "0", "width": "1024", "height": "768"},
                        text=None,
                        source=SourceRef(
                            file_path="auto-risk.xml",
                            node_path="/Screen[1]/Contents[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="UnknownWidget",
                                attributes={
                                    "id": "unknown1",
                                    "left": "24",
                                    "top": "24",
                                    "width": "140",
                                    "height": "40",
                                    "onclick": "fnUnknownOne",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="auto-risk.xml",
                                    node_path="/Screen[1]/Contents[1]/UnknownWidget[1]",
                                    line=3,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="UnknownWidget",
                                attributes={
                                    "id": "unknown2",
                                    "left": "24",
                                    "top": "72",
                                    "width": "140",
                                    "height": "40",
                                    "oncontextmenu": "fnUnknownTwo",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="auto-risk.xml",
                                    node_path="/Screen[1]/Contents[1]/UnknownWidget[2]",
                                    line=4,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="Tab",
                                attributes={
                                    "id": "tabRisk",
                                    "left": "200",
                                    "top": "24",
                                    "width": "400",
                                    "height": "300",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="auto-risk.xml",
                                    node_path="/Screen[1]/Contents[1]/Tab[1]",
                                    line=5,
                                ),
                                children=[
                                    AstNode(
                                        tag="TabPage",
                                        attributes={"id": "pageA", "text": "A"},
                                        text=None,
                                        source=SourceRef(
                                            file_path="auto-risk.xml",
                                            node_path="/Screen[1]/Contents[1]/Tab[1]/TabPage[1]",
                                            line=6,
                                        ),
                                        children=[],
                                    ),
                                    AstNode(
                                        tag="TabPage",
                                        attributes={"id": "pageB", "text": "B"},
                                        text=None,
                                        source=SourceRef(
                                            file_path="auto-risk.xml",
                                            node_path="/Screen[1]/Contents[1]/Tab[1]/TabPage[2]",
                                            line=7,
                                        ),
                                        children=[],
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            ),
            events=[
                EventIR(
                    node_tag="UnknownWidget",
                    node_id="unknown1",
                    event_name="onclick",
                    handler="fnUnknownOne",
                    source=SourceRef(
                        file_path="auto-risk.xml",
                        node_path="/Screen[1]/Contents[1]/UnknownWidget[1]",
                        line=3,
                    ),
                ),
                EventIR(
                    node_tag="UnknownWidget",
                    node_id="unknown2",
                    event_name="oncontextmenu",
                    handler="fnUnknownTwo",
                    source=SourceRef(
                        file_path="auto-risk.xml",
                        node_path="/Screen[1]/Contents[1]/UnknownWidget[2]",
                        line=4,
                    ),
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="auto-risk.xml",
                out_dir=out_dir,
                mode="auto",
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertEqual(report.requested_mode, "auto")
            self.assertEqual(report.mode, "strict")
            self.assertIn("auto_selected_strict_high_fidelity_risk", report.decision_reason)
            self.assertEqual(report.auto_risk_threshold, 0.58)
            self.assertGreaterEqual(report.risk_score, 0.58)
            self.assertGreater(report.risk_signal_scores["fallback_nodes"], 0.0)
            self.assertGreater(report.risk_signal_scores["tab_nodes"], 0.0)
            self.assertEqual(report.risk_signal_scores["total"], report.risk_score)
            self.assertNotIn('from "@mui/material"', tsx_text)
            self.assertIn("onClick={() => setTabIndex0(0)}", tsx_text)
            self.assertIn(
                (
                    "Unsupported widget tag 'UnknownWidget' at "
                    "/Screen[1]/Contents[1]/UnknownWidget[1]; rendered as fallback widget."
                ),
                report.warnings,
            )

    def test_generate_ui_codegen_artifacts_auto_mode_respects_threshold_override(self) -> None:
        parsed = parse_xml_file(FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            default_report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir / "default-auto",
                mode="auto",
            )
            low_threshold_report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir / "low-threshold-auto",
                mode="auto",
                auto_risk_threshold=0.10,
            )
            high_threshold_report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir / "high-threshold-auto",
                mode="auto",
                auto_risk_threshold=0.95,
            )

            self.assertEqual(default_report.mode, "mui")
            self.assertEqual(default_report.auto_risk_threshold, 0.58)
            self.assertEqual(low_threshold_report.mode, "strict")
            self.assertEqual(low_threshold_report.auto_risk_threshold, 0.1)
            self.assertEqual(high_threshold_report.mode, "mui")
            self.assertEqual(high_threshold_report.auto_risk_threshold, 0.95)

    def test_generate_ui_codegen_artifacts_explicit_modes_ignore_auto_policy_threshold(
        self,
    ) -> None:
        parsed = parse_xml_file(FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            strict_report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir / "strict",
                mode="strict",
                auto_risk_threshold=0.01,
            )
            mui_report = generate_ui_codegen_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir / "mui",
                mode="mui",
                auto_risk_threshold=0.01,
            )

            self.assertEqual(strict_report.mode, "strict")
            self.assertEqual(strict_report.auto_risk_threshold, 0.01)
            self.assertIn("explicit_strict_mode", strict_report.decision_reason)
            self.assertEqual(mui_report.mode, "mui")
            self.assertEqual(mui_report.auto_risk_threshold, 0.01)
            self.assertIn("explicit_mui_mode", mui_report.decision_reason)

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
                    '<Box className="mi-widget mi-widget-edit" component="input" type="text" '
                    'aria-label={"Keyword"} style={{"height": "100%", "width": "100%"}} '
                    'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                    'defaultValue={"A-100"} />'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    '<Box className="mi-widget mi-widget-combo" component="select" '
                    'aria-label={"Status"} style={{"height": "100%", "width": "100%"}} '
                    'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                    'defaultValue={""}>'
                ),
                tsx_text,
            )
            self.assertIn(
                'className="mi-widget mi-widget-grid" style={{"height": "100%", "width": "100%"}}',
                tsx_text,
            )

    def test_generate_ui_codegen_artifacts_normalizes_legacy_right_bottom_coordinates(self) -> None:
        screen = ScreenIR(
            screen_id="Legacy Coordinate Normalization",
            root=AstNode(
                tag="Screen",
                attributes={"id": "LegacyCoordinateNormalization"},
                text=None,
                source=SourceRef(file_path="coords.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Contents",
                        attributes={},
                        text=None,
                        source=SourceRef(
                            file_path="coords.xml",
                            node_path="/Screen[1]/Contents[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Grid",
                                attributes={
                                    "id": "grdPrimary",
                                    "left": "20",
                                    "right": "220",
                                    "width": "200",
                                    "top": "10",
                                    "bottom": "110",
                                    "height": "100",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="coords.xml",
                                    node_path="/Screen[1]/Contents[1]/Grid[1]",
                                    line=3,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="Edit",
                                attributes={
                                    "id": "edtInferredLeft",
                                    "right": "180",
                                    "width": "80",
                                    "top": "124",
                                    "height": "20",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="coords.xml",
                                    node_path="/Screen[1]/Contents[1]/Edit[1]",
                                    line=4,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="Static",
                                attributes={
                                    "id": "staAnchor",
                                    "left": "24",
                                    "right": "24",
                                    "top": "160",
                                    "text": "Anchor",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="coords.xml",
                                    node_path="/Screen[1]/Contents[1]/Static[1]",
                                    line=5,
                                ),
                                children=[],
                            ),
                        ],
                    )
                ],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="coords.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn(
                (
                    'style={{"height": "100px", "left": "20px", "position": "absolute", '
                    '"top": "10px", "width": "200px"}}'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    'style={{"height": "20px", "left": "100px", "position": "absolute", '
                    '"top": "124px", "width": "80px"}}'
                ),
                tsx_text,
            )
            self.assertIn(
                (
                    'style={{"left": "24px", "position": "absolute", '
                    '"right": "24px", "top": "160px"}}'
                ),
                tsx_text,
            )

    def test_generate_ui_codegen_artifacts_normalizes_text_align_values(self) -> None:
        screen = ScreenIR(
            screen_id="Text Align Normalization",
            root=AstNode(
                tag="Screen",
                attributes={"id": "TextAlignNormalization"},
                text=None,
                source=SourceRef(file_path="align.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Contents",
                        attributes={},
                        text=None,
                        source=SourceRef(
                            file_path="align.xml",
                            node_path="/Screen[1]/Contents[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Static",
                                attributes={
                                    "id": "staRight",
                                    "text": "Right",
                                    "left": "8",
                                    "top": "8",
                                    "width": "120",
                                    "height": "24",
                                    "align": "RIGHT",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="align.xml",
                                    node_path="/Screen[1]/Contents[1]/Static[1]",
                                    line=3,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="Static",
                                attributes={
                                    "id": "staCenter",
                                    "text": "Center",
                                    "left": "8",
                                    "top": "40",
                                    "width": "120",
                                    "height": "24",
                                    "textalign": "centre",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="align.xml",
                                    node_path="/Screen[1]/Contents[1]/Static[2]",
                                    line=4,
                                ),
                                children=[],
                            ),
                            AstNode(
                                tag="Static",
                                attributes={
                                    "id": "staUnknown",
                                    "text": "Unknown",
                                    "left": "8",
                                    "top": "72",
                                    "width": "120",
                                    "height": "24",
                                    "textalign": "MiddleCenter",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="align.xml",
                                    node_path="/Screen[1]/Contents[1]/Static[3]",
                                    line=5,
                                ),
                                children=[],
                            ),
                        ],
                    )
                ],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="align.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn('"textAlign": "right"', tsx_text)
            self.assertIn('"textAlign": "center"', tsx_text)
            self.assertNotIn('"textAlign": "middlecenter"', tsx_text)

    def test_generate_ui_codegen_artifacts_maps_legacy_widget_aliases_and_ignores_meta_tags(
        self,
    ) -> None:
        screen = ScreenIR(
            screen_id="Legacy Widget Aliases",
            root=AstNode(
                tag="Screen",
                attributes={"id": "LegacyWidgetAliases"},
                text=None,
                source=SourceRef(file_path="legacy.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Window",
                        attributes={"id": "winMain"},
                        text=None,
                        source=SourceRef(
                            file_path="legacy.xml",
                            node_path="/Screen[1]/Window[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Form",
                                attributes={"id": "frmMain"},
                                text=None,
                                source=SourceRef(
                                    file_path="legacy.xml",
                                    node_path="/Screen[1]/Window[1]/Form[1]",
                                    line=3,
                                ),
                                children=[
                                    AstNode(
                                        tag="Div",
                                        attributes={"id": "divMain"},
                                        text=None,
                                        source=SourceRef(
                                            file_path="legacy.xml",
                                            node_path="/Screen[1]/Window[1]/Form[1]/Div[1]",
                                            line=4,
                                        ),
                                        children=[
                                            AstNode(
                                                tag="TextArea",
                                                attributes={
                                                    "id": "txtMemo",
                                                    "text": "Memo",
                                                    "rows": "4",
                                                    "value": "sample",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/TextArea[1]",
                                                    line=5,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="MaskEdit",
                                                attributes={
                                                    "id": "mskDate",
                                                    "text": "Date",
                                                    "mask": "9999-99-99",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/MaskEdit[1]",
                                                    line=6,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="Image",
                                                attributes={
                                                    "id": "imgLogo",
                                                    "text": "Logo",
                                                    "src": "/assets/logo.png",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Image[1]",
                                                    line=7,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="Radio",
                                                attributes={"id": "rdoType", "text": "Type"},
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Radio[1]",
                                                    line=8,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="Checkbox",
                                                attributes={
                                                    "id": "chkAgree",
                                                    "text": "Agree",
                                                    "value": "true",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Checkbox[1]",
                                                    line=8,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="Calendar",
                                                attributes={
                                                    "id": "calStart",
                                                    "text": "Start",
                                                    "value": "2026-02-13",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Calendar[1]",
                                                    line=8,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="Spin",
                                                attributes={"id": "spnQty", "text": "Qty", "value": "1"},
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Spin[1]",
                                                    line=8,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="WebBrowser",
                                                attributes={
                                                    "id": "wbHelp",
                                                    "text": "Help",
                                                    "url": "https://example.com",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/WebBrowser[1]",
                                                    line=8,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="TreeView",
                                                attributes={"id": "trvMenu", "text": "Menu"},
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/TreeView[1]",
                                                    line=8,
                                                ),
                                                children=[],
                                            ),
                                            AstNode(
                                                tag="Grid",
                                                attributes={
                                                    "id": "grdOrders",
                                                    "text": "Orders",
                                                    "binddataset": "dsOrder",
                                                },
                                                text=None,
                                                source=SourceRef(
                                                    file_path="legacy.xml",
                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]",
                                                    line=9,
                                                ),
                                                children=[
                                                    AstNode(
                                                        tag="colinfo",
                                                        attributes={},
                                                        text=None,
                                                        source=SourceRef(
                                                            file_path="legacy.xml",
                                                            node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/colinfo[1]",
                                                            line=10,
                                                        ),
                                                        children=[
                                                            AstNode(
                                                                tag="col",
                                                                attributes={"id": "orderNo"},
                                                                text=None,
                                                                source=SourceRef(
                                                                    file_path="legacy.xml",
                                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/colinfo[1]/col[1]",
                                                                    line=11,
                                                                ),
                                                                children=[],
                                                            ),
                                                            AstNode(
                                                                tag="col",
                                                                attributes={"id": "status"},
                                                                text=None,
                                                                source=SourceRef(
                                                                    file_path="legacy.xml",
                                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/colinfo[1]/col[2]",
                                                                    line=12,
                                                                ),
                                                                children=[],
                                                            ),
                                                        ],
                                                    ),
                                                    AstNode(
                                                        tag="format",
                                                        attributes={},
                                                        text=None,
                                                        source=SourceRef(
                                                            file_path="legacy.xml",
                                                            node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/format[1]",
                                                            line=13,
                                                        ),
                                                        children=[
                                                            AstNode(
                                                                tag="head",
                                                                attributes={},
                                                                text=None,
                                                                source=SourceRef(
                                                                    file_path="legacy.xml",
                                                                    node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/format[1]/head[1]",
                                                                    line=14,
                                                                ),
                                                                children=[
                                                                    AstNode(
                                                                        tag="cell",
                                                                        attributes={"text": "Order No"},
                                                                        text=None,
                                                                        source=SourceRef(
                                                                            file_path="legacy.xml",
                                                                            node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/format[1]/head[1]/cell[1]",
                                                                            line=15,
                                                                        ),
                                                                        children=[],
                                                                    ),
                                                                    AstNode(
                                                                        tag="cell",
                                                                        attributes={"text": "Status"},
                                                                        text=None,
                                                                        source=SourceRef(
                                                                            file_path="legacy.xml",
                                                                            node_path="/Screen[1]/Window[1]/Form[1]/Div[1]/Grid[1]/format[1]/head[1]/cell[2]",
                                                                            line=16,
                                                                        ),
                                                                        children=[],
                                                                    ),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    )
                                ],
                            )
                        ],
                    ),
                    AstNode(
                        tag="Dataset",
                        attributes={"id": "dsOrder"},
                        text=None,
                        source=SourceRef(
                            file_path="legacy.xml",
                            node_path="/Screen[1]/Dataset[1]",
                            line=17,
                        ),
                        children=[
                            AstNode(
                                tag="record",
                                attributes={},
                                text=None,
                                source=SourceRef(
                                    file_path="legacy.xml",
                                    node_path="/Screen[1]/Dataset[1]/record[1]",
                                    line=18,
                                ),
                                children=[],
                            )
                        ],
                    ),
                    AstNode(
                        tag="Script",
                        attributes={},
                        text="function noop() {}",
                        source=SourceRef(
                            file_path="legacy.xml",
                            node_path="/Screen[1]/Script[1]",
                            line=19,
                        ),
                        children=[],
                    ),
                ],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="legacy.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn('className="mi-widget mi-widget-textarea"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-maskedit"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-image"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-radio"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-checkbox"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-calendar"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-spin"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-webbrowser"', tsx_text)
            self.assertIn('className="mi-widget mi-widget-treeview"', tsx_text)
            self.assertIn('component="img"', tsx_text)
            self.assertIn('src={"/assets/logo.png"}', tsx_text)
            self.assertIn('component="iframe"', tsx_text)
            self.assertIn('src={"https://example.com"}', tsx_text)
            self.assertIn(
                '<TableCell sx={{ whiteSpace: "nowrap" }}>{"Order No"}</TableCell>',
                tsx_text,
            )
            self.assertIn(
                '<TableCell sx={{ whiteSpace: "nowrap" }}>{"Status"}</TableCell>',
                tsx_text,
            )
            self.assertIn('data-mi-widget={"ignored"}', tsx_text)
            self.assertIn('className="mi-widget-shell mi-widget-shell-dataset"', tsx_text)
            self.assertIn('style={{"display": "none"}}', tsx_text)

            self.assertNotIn('className="mi-widget mi-widget-fallback"', tsx_text)
            self.assertNotIn("Unsupported tag: Window", tsx_text)
            self.assertNotIn("Unsupported tag: Form", tsx_text)
            self.assertNotIn("Unsupported tag: TextArea", tsx_text)
            self.assertNotIn("Unsupported tag: Dataset", tsx_text)
            self.assertNotIn("Unsupported tag: Script", tsx_text)
            self.assertEqual(report.warnings, [])

    def test_generate_ui_codegen_artifacts_wires_tab_page_switching_state(self) -> None:
        screen = ScreenIR(
            screen_id="Tab Page Visibility",
            root=AstNode(
                tag="Screen",
                attributes={"id": "TabPageVisibility"},
                text=None,
                source=SourceRef(file_path="tab.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Tab",
                        attributes={"id": "tabMain"},
                        text=None,
                        source=SourceRef(
                            file_path="tab.xml",
                            node_path="/Screen[1]/Tab[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Contents",
                                attributes={},
                                text=None,
                                source=SourceRef(
                                    file_path="tab.xml",
                                    node_path="/Screen[1]/Tab[1]/Contents[1]",
                                    line=3,
                                ),
                                children=[
                                    AstNode(
                                        tag="TabPage",
                                        attributes={"id": "page1", "text": "Page 1"},
                                        text=None,
                                        source=SourceRef(
                                            file_path="tab.xml",
                                            node_path="/Screen[1]/Tab[1]/Contents[1]/TabPage[1]",
                                            line=4,
                                        ),
                                        children=[],
                                    ),
                                    AstNode(
                                        tag="TabPage",
                                        attributes={"id": "page2", "text": "Page 2"},
                                        text=None,
                                        source=SourceRef(
                                            file_path="tab.xml",
                                            node_path="/Screen[1]/Tab[1]/Contents[1]/TabPage[2]",
                                            line=5,
                                        ),
                                        children=[],
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="tab.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn('import { useState, type JSX } from "react";', tsx_text)
            self.assertIn("Tab as MuiTab, Tabs", tsx_text)
            self.assertIn("const [tabIndex0, setTabIndex0] = useState<number>(0);", tsx_text)
            self.assertIn(
                '<Tabs value={tabIndex0} onChange={(_event, nextIndex) => setTabIndex0(nextIndex)}',
                tsx_text,
            )
            self.assertIn('<MuiTab label={"Page 1"} />', tsx_text)
            self.assertIn('<MuiTab label={"Page 2"} />', tsx_text)
            page1_anchor = (
                'data-mi-source-node={"/Screen[1]/Tab[1]/Contents[1]/TabPage[1]"} '
                'data-mi-source-file={"tab.xml"}'
            )
            page2_anchor = (
                'data-mi-source-node={"/Screen[1]/Tab[1]/Contents[1]/TabPage[2]"} '
                'data-mi-source-file={"tab.xml"}'
            )
            self.assertIn(page1_anchor, tsx_text)
            self.assertIn(page2_anchor, tsx_text)
            self.assertIn(
                'data-mi-attrs={"id=page1, text=Page 1"} style={{"position": "relative"}}',
                tsx_text,
            )
            self.assertIn(
                'data-mi-attrs={"id=page2, text=Page 2"} style={{"position": "relative"}}',
                tsx_text,
            )
            self.assertIn("{tabIndex0 === 0 ? (", tsx_text)
            self.assertIn(
                '{/* source file=tab.xml node=/Screen[1]/Tab[1]/Contents[1]/TabPage[1] line=4 */}',
                tsx_text,
            )
            self.assertIn("{tabIndex0 === 1 ? (", tsx_text)
            self.assertIn(
                '{/* source file=tab.xml node=/Screen[1]/Tab[1]/Contents[1]/TabPage[2] line=5 */}',
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
            self.assertEqual(report.summary.total_event_attributes, 2)
            self.assertEqual(report.summary.runtime_wired_event_props, 2)
            self.assertEqual(report.summary.unsupported_event_bindings, 0)

    def test_generate_ui_codegen_artifacts_wires_extended_react_event_props(self) -> None:
        screen = ScreenIR(
            screen_id="Extended Events",
            root=AstNode(
                tag="Screen",
                attributes={"id": "ExtendedEvents"},
                text=None,
                source=SourceRef(file_path="extended.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Contents",
                        attributes={},
                        text=None,
                        source=SourceRef(
                            file_path="extended.xml",
                            node_path="/Screen[1]/Contents[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Button",
                                attributes={
                                    "id": "btnExtended",
                                    "text": "Extended",
                                    "oncontextmenu": "fnOpenContext",
                                    "ondragstart": "fnDragStart",
                                    "onwheel": "fnWheel",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="extended.xml",
                                    node_path="/Screen[1]/Contents[1]/Button[1]",
                                    line=3,
                                ),
                                children=[],
                            ),
                        ],
                    ),
                ],
            ),
            events=[
                EventIR(
                    node_tag="Button",
                    node_id="btnExtended",
                    event_name="oncontextmenu",
                    handler="fnOpenContext",
                    source=SourceRef(
                        file_path="extended.xml",
                        node_path="/Screen[1]/Contents[1]/Button[1]",
                        line=3,
                    ),
                ),
                EventIR(
                    node_tag="Button",
                    node_id="btnExtended",
                    event_name="ondragstart",
                    handler="fnDragStart",
                    source=SourceRef(
                        file_path="extended.xml",
                        node_path="/Screen[1]/Contents[1]/Button[1]",
                        line=3,
                    ),
                ),
                EventIR(
                    node_tag="Button",
                    node_id="btnExtended",
                    event_name="onwheel",
                    handler="fnWheel",
                    source=SourceRef(
                        file_path="extended.xml",
                        node_path="/Screen[1]/Contents[1]/Button[1]",
                        line=3,
                    ),
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="extended.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn('onContextMenu={behaviorStore.onFnOpenContext}', tsx_text)
            self.assertIn('onDragStart={behaviorStore.onFnDragStart}', tsx_text)
            self.assertIn('onWheel={behaviorStore.onFnWheel}', tsx_text)
            self.assertIn('data-mi-action-oncontextmenu={"onFnOpenContext"}', tsx_text)
            self.assertIn('data-mi-action-ondragstart={"onFnDragStart"}', tsx_text)
            self.assertIn('data-mi-action-onwheel={"onFnWheel"}', tsx_text)
            self.assertEqual(report.summary.wired_event_bindings, 3)
            self.assertEqual(report.summary.total_event_attributes, 3)
            self.assertEqual(report.summary.runtime_wired_event_props, 3)
            self.assertEqual(report.summary.unsupported_event_bindings, 0)
            self.assertEqual(report.unsupported_event_inventory, [])

    def test_generate_ui_codegen_artifacts_reports_structured_unsupported_event_inventory(self) -> None:
        screen = ScreenIR(
            screen_id="Unsupported Events",
            root=AstNode(
                tag="Screen",
                attributes={"id": "UnsupportedEvents"},
                text=None,
                source=SourceRef(file_path="unsupported.xml", node_path="/Screen[1]", line=1),
                children=[
                    AstNode(
                        tag="Contents",
                        attributes={},
                        text=None,
                        source=SourceRef(
                            file_path="unsupported.xml",
                            node_path="/Screen[1]/Contents[1]",
                            line=2,
                        ),
                        children=[
                            AstNode(
                                tag="Button",
                                attributes={
                                    "id": "btnUnsupported",
                                    "text": "Unsupported",
                                    "onclick": "fnClick",
                                    "onhotkey": "fnHotkey",
                                    "onitemchanged": "fnItemChanged",
                                },
                                text=None,
                                source=SourceRef(
                                    file_path="unsupported.xml",
                                    node_path="/Screen[1]/Contents[1]/Button[1]",
                                    line=3,
                                ),
                                children=[],
                            ),
                        ],
                    ),
                ],
            ),
            events=[
                EventIR(
                    node_tag="Button",
                    node_id="btnUnsupported",
                    event_name="onclick",
                    handler="fnClick",
                    source=SourceRef(
                        file_path="unsupported.xml",
                        node_path="/Screen[1]/Contents[1]/Button[1]",
                        line=3,
                    ),
                ),
                EventIR(
                    node_tag="Button",
                    node_id="btnUnsupported",
                    event_name="onitemchanged",
                    handler="fnItemChanged",
                    source=SourceRef(
                        file_path="unsupported.xml",
                        node_path="/Screen[1]/Contents[1]/Button[1]",
                        line=3,
                    ),
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report = generate_ui_codegen_artifacts(
                screen=screen,
                input_xml_path="unsupported.xml",
                out_dir=out_dir,
            )

            tsx_text = Path(report.tsx_file).read_text(encoding="utf-8")
            self.assertIn('onClick={behaviorStore.onFnClick}', tsx_text)
            self.assertIn('data-mi-action-onitemchanged={"onFnItemChanged"}', tsx_text)
            self.assertNotIn("onItemChanged={", tsx_text)

            self.assertEqual(report.summary.wired_event_bindings, 2)
            self.assertEqual(report.summary.total_event_attributes, 3)
            self.assertEqual(report.summary.runtime_wired_event_props, 1)
            self.assertEqual(report.summary.unsupported_event_bindings, 2)
            self.assertEqual(len(report.unsupported_event_inventory), 2)

            self.assertEqual(report.unsupported_event_inventory[0].event_name, "onhotkey")
            self.assertEqual(
                report.unsupported_event_inventory[0].reason,
                "missing_behavior_action_binding",
            )
            self.assertIsNone(report.unsupported_event_inventory[0].action_name)

            self.assertEqual(report.unsupported_event_inventory[1].event_name, "onitemchanged")
            self.assertEqual(
                report.unsupported_event_inventory[1].reason,
                "missing_react_event_mapping",
            )
            self.assertEqual(
                report.unsupported_event_inventory[1].action_name,
                "onFnItemChanged",
            )

            self.assertIn(
                (
                    "No behavior action binding resolved for event 'onhotkey' at "
                    "/Screen[1]/Contents[1]/Button[1]; runtime handler not wired."
                ),
                report.warnings,
            )
            self.assertIn(
                (
                    "No React event mapping for 'onitemchanged' at "
                    "/Screen[1]/Contents[1]/Button[1]; action 'onFnItemChanged' trace emitted only."
                ),
                report.warnings,
            )


if __name__ == "__main__":
    unittest.main()
