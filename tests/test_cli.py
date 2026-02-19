from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.cli import main  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"
KNOWN_TAGS = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS = FIXTURES_DIR / "known_attrs_all.json"


class TestCli(unittest.TestCase):
    def test_parse_command_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "report.json"
            rc = main(
                [
                    "parse",
                    str(FIXTURE_XML),
                    "--out",
                    str(out_file),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out_file.exists())

            payload = json.loads(out_file.read_text(encoding="utf-8"))
            gate_names = {gate["name"] for gate in payload["gates"]}
            self.assertIn("canonical_roundtrip_hash_match", gate_names)
            self.assertIn("transaction_extraction_coverage", gate_names)
            self.assertIn("script_extraction_coverage", gate_names)

    def test_batch_parse_reports_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "input"
            out_dir = Path(tmp_dir) / "reports"
            summary_out = Path(tmp_dir) / "summary.json"
            input_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(FIXTURE_XML, input_dir / "good.xml")
            (input_dir / "broken.xml").write_text("<Screen><Broken>", encoding="utf-8")

            rc = main(
                [
                    "batch-parse",
                    str(input_dir),
                    "--out-dir",
                    str(out_dir),
                    "--summary-out",
                    str(summary_out),
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            self.assertTrue(summary_out.exists())
            payload = json.loads(summary_out.read_text(encoding="utf-8"))
            broken_file = str((input_dir / "broken.xml").resolve())
            self.assertEqual(payload["total_xml_files"], 2)
            self.assertEqual(payload["reports_written"], 1)
            self.assertEqual(len(payload["failures"]), 1)
            self.assertIn("gate_pass_fail_counts", payload)
            self.assertIn("failure_reason_counts", payload)
            self.assertIn("failure_file_counts", payload)
            self.assertIn("failure_file_leaderboard", payload)
            self.assertEqual(payload["failure_reason_counts"]["xml_parse_failure"], 1)
            self.assertEqual(payload["gate_pass_fail_counts"]["unknown_tag_count"]["pass_count"], 1)
            self.assertEqual(payload["gate_pass_fail_counts"]["unknown_tag_count"]["fail_count"], 0)
            self.assertEqual(payload["failure_file_counts"][broken_file], 1)
            self.assertTrue((out_dir / "good.json").exists())

    def test_batch_parse_aggregates_gate_failures_and_leaderboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "input"
            out_dir = Path(tmp_dir) / "reports"
            summary_out = Path(tmp_dir) / "summary.json"
            input_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(FIXTURE_XML, input_dir / "good.xml")
            (input_dir / "strict_fail.xml").write_text(
                "<Screen><UnknownWidget /></Screen>",
                encoding="utf-8",
            )
            (input_dir / "broken.xml").write_text("<Screen><Broken>", encoding="utf-8")

            rc = main(
                [
                    "batch-parse",
                    str(input_dir),
                    "--out-dir",
                    str(out_dir),
                    "--summary-out",
                    str(summary_out),
                    "--strict",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            payload = json.loads(summary_out.read_text(encoding="utf-8"))
            strict_fail_file = str((input_dir / "strict_fail.xml").resolve())
            broken_file = str((input_dir / "broken.xml").resolve())
            self.assertEqual(payload["total_xml_files"], 3)
            self.assertEqual(payload["reports_written"], 1)
            self.assertEqual(len(payload["failures"]), 2)
            self.assertEqual(payload["failure_reason_counts"]["strict_gate_failure"], 1)
            self.assertEqual(payload["failure_reason_counts"]["xml_parse_failure"], 1)

            unknown_tag_gate = payload["gate_pass_fail_counts"]["unknown_tag_count"]
            self.assertEqual(unknown_tag_gate["pass_count"], 1)
            self.assertEqual(unknown_tag_gate["fail_count"], 1)

            strict_failure = next(
                item
                for item in payload["failures"]
                if item["file"] == strict_fail_file
            )
            self.assertIn("unknown_tag_count", strict_failure["failed_gates"])

            leaderboard = payload["failure_file_leaderboard"]
            self.assertGreaterEqual(len(leaderboard), 2)
            self.assertEqual(leaderboard[0]["file"], strict_fail_file)
            self.assertGreaterEqual(leaderboard[0]["failed_gate_count"], 1)
            self.assertIn("strict_gate_failure", leaderboard[0]["failure_reasons"])

            broken_entry = next(
                item
                for item in leaderboard
                if item["file"] == broken_file
            )
            self.assertEqual(broken_entry["failed_gate_count"], 0)
            self.assertIn("xml_parse_failure", broken_entry["failure_reasons"])
            self.assertTrue((out_dir / "good.json").exists())

    def test_map_api_generates_route_service_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-api"
            report_out = Path(tmp_dir) / "mapping-report.json"
            rc = main(
                [
                    "map-api",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue(report_out.exists())
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_transactions"], 1)
            self.assertEqual(payload["summary"]["mapped_success"], 1)
            self.assertEqual(payload["summary"]["mapped_failure"], 0)
            self.assertEqual(payload["summary"]["unsupported"], 0)
            self.assertEqual(payload["results"][0]["status"], "success")

            route_file = out_dir / "src" / "routes" / "simple-screen-fixture.routes.js"
            service_file = out_dir / "src" / "services" / "simple-screen-fixture.service.js"
            self.assertTrue(route_file.exists())
            self.assertTrue(service_file.exists())
            self.assertIn(
                'router.post("/api/orders/search"',
                route_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "async function svcOrderSearch(req)",
                service_file.read_text(encoding="utf-8"),
            )

    def test_map_api_returns_failure_when_mapping_has_missing_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "broken.xml"
            xml_path.write_text(
                "<Screen id='Broken'><Transaction id='tx1' serviceid='SVC_TX1' method='POST' /></Screen>",
                encoding="utf-8",
            )
            out_dir = Path(tmp_dir) / "generated-api"
            report_out = Path(tmp_dir) / "mapping-report.json"

            rc = main(
                [
                    "map-api",
                    str(xml_path),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_transactions"], 1)
            self.assertEqual(payload["summary"]["mapped_success"], 0)
            self.assertEqual(payload["summary"]["mapped_failure"], 1)
            self.assertEqual(payload["summary"]["unsupported"], 0)
            self.assertEqual(payload["results"][0]["reason"], "missing_endpoint")

    def test_migrate_e2e_success_writes_consolidated_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            out_dir = workspace / "out"
            api_out_dir = workspace / "generated-api"
            ui_out_dir = workspace / "generated-ui"
            preview_host_dir = workspace / "preview-host"
            preview_host_dir.mkdir(parents=True, exist_ok=True)

            rc = main(
                [
                    "migrate-e2e",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(out_dir),
                    "--api-out-dir",
                    str(api_out_dir),
                    "--ui-out-dir",
                    str(ui_out_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            summary_out = out_dir / "simple_screen_fixture.migration-summary.json"
            self.assertTrue(summary_out.exists())
            payload = json.loads(summary_out.read_text(encoding="utf-8"))

            self.assertEqual(payload["command"], "migrate-e2e")
            self.assertEqual(payload["overall_status"], "success")
            self.assertEqual(payload["overall_exit_code"], 0)
            self.assertEqual(payload["stages"]["parse"]["status"], "success")
            self.assertEqual(payload["stages"]["map_api"]["status"], "success")
            self.assertEqual(payload["stages"]["gen_ui"]["status"], "success")
            self.assertEqual(payload["stages"]["fidelity_audit"]["status"], "success")
            self.assertEqual(payload["stages"]["sync_preview"]["status"], "success")
            self.assertEqual(payload["stages"]["preview_smoke"]["status"], "success")
            self.assertEqual(payload["stages"]["preview_smoke"]["unresolved_module_count"], 0)

            reports = payload["reports"]
            self.assertTrue(Path(reports["parse_report"]).exists())
            self.assertTrue(Path(reports["map_api_report"]).exists())
            self.assertTrue(Path(reports["gen_ui_report"]).exists())
            self.assertTrue(Path(reports["fidelity_audit_report"]).exists())
            self.assertTrue(Path(reports["preview_sync_report"]).exists())
            self.assertTrue(Path(reports["preview_smoke_report"]).exists())
            self.assertEqual(Path(reports["consolidated_summary"]), summary_out.resolve())

            self.assertEqual(
                payload["stages"]["gen_ui"]["behavior_store_hook"],
                "useSimpleScreenFixtureBehaviorStore",
            )
            self.assertEqual(payload["stages"]["gen_ui"]["wired_event_bindings"], 1)
            self.assertEqual(payload["stages"]["gen_ui"]["total_event_attributes"], 1)
            self.assertEqual(payload["stages"]["gen_ui"]["runtime_wired_event_props"], 1)
            self.assertEqual(payload["stages"]["gen_ui"]["unsupported_event_bindings"], 0)

            generated_files = set(payload["generated_file_references"])
            self.assertIn(str((api_out_dir / "src" / "routes" / "simple-screen-fixture.routes.js").resolve()), generated_files)
            self.assertIn(str((api_out_dir / "src" / "services" / "simple-screen-fixture.service.js").resolve()), generated_files)
            self.assertIn(str((ui_out_dir / "src" / "screens" / "simple-screen-fixture.tsx").resolve()), generated_files)
            self.assertIn(str((ui_out_dir / "src" / "behavior" / "simple-screen-fixture.store.ts").resolve()), generated_files)
            self.assertIn(str((ui_out_dir / "src" / "behavior" / "simple-screen-fixture.actions.ts").resolve()), generated_files)
            self.assertIn(
                str((preview_host_dir / "src" / "manifest" / "screens.manifest.json").resolve()),
                generated_files,
            )
            self.assertIn(
                str((preview_host_dir / "src" / "screens" / "registry.generated.ts").resolve()),
                generated_files,
            )

    def test_migrate_e2e_returns_failure_when_map_api_has_mapping_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_path = workspace / "broken.xml"
            xml_path.write_text(
                "<Screen id='Broken'><Transaction id='tx1' serviceid='SVC_TX1' method='POST' /></Screen>",
                encoding="utf-8",
            )

            out_dir = workspace / "out"
            api_out_dir = workspace / "generated-api"
            ui_out_dir = workspace / "generated-ui"
            preview_host_dir = workspace / "preview-host"
            preview_host_dir.mkdir(parents=True, exist_ok=True)

            rc = main(
                [
                    "migrate-e2e",
                    str(xml_path),
                    "--out-dir",
                    str(out_dir),
                    "--api-out-dir",
                    str(api_out_dir),
                    "--ui-out-dir",
                    str(ui_out_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            summary_out = out_dir / "broken.migration-summary.json"
            self.assertTrue(summary_out.exists())
            payload = json.loads(summary_out.read_text(encoding="utf-8"))

            self.assertEqual(payload["overall_status"], "failure")
            self.assertEqual(payload["overall_exit_code"], 2)
            self.assertEqual(payload["stages"]["parse"]["status"], "success")
            self.assertEqual(payload["stages"]["map_api"]["status"], "failure")
            self.assertEqual(payload["stages"]["map_api"]["mapped_failure"], 1)
            self.assertEqual(payload["stages"]["gen_ui"]["status"], "success")
            self.assertEqual(payload["stages"]["fidelity_audit"]["status"], "success")
            self.assertEqual(payload["stages"]["sync_preview"]["status"], "success")
            self.assertEqual(payload["stages"]["preview_smoke"]["status"], "success")
            self.assertIn("map_api: mapping failures detected (1)", payload["errors"])

    def test_prototype_accept_command_returns_pass_for_clean_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            actions_file = workspace / "clean.actions.ts"
            actions_file.write_text(
                "export function createScreenBehaviorActions() { return {}; }\n",
                encoding="utf-8",
            )
            summary_file = workspace / "clean.migration-summary.json"
            summary_file.write_text(
                json.dumps(
                    {
                        "screen_id": "CleanScreen",
                        "overall_status": "success",
                        "stages": {
                            "map_api": {
                                "total_transactions": 1,
                            },
                            "fidelity_audit": {
                                "risk_detected": False,
                                "missing_node_count": 0,
                                "position_style_nodes_with_risk": 0,
                            },
                            "gen_ui": {
                                "total_event_attributes": 2,
                                "runtime_wired_event_props": 2,
                                "unsupported_event_bindings": 0,
                                "behavior_actions_file": str(actions_file),
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            report_out = workspace / "prototype-acceptance.json"

            rc = main(
                [
                    "prototype-accept",
                    str(summary_file),
                    "--report-out",
                    str(report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["verdict"], "pass")
            self.assertEqual(payload["totals"]["total_migration_summaries"], 1)
            self.assertEqual(payload["totals"]["fidelity_risk_count"], 0)
            self.assertEqual(payload["totals"]["unsupported_event_bindings"], 0)
            self.assertEqual(payload["totals"]["unresolved_transaction_adapter_signals"], 0)

    def test_prototype_accept_command_returns_failure_for_risk_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            actions_file = workspace / "risk.actions.ts"
            actions_file.write_text(
                'const marker = "UNIMPLEMENTED_TRANSACTION_ADAPTER";\n',
                encoding="utf-8",
            )
            summary_file = workspace / "risk.migration-summary.json"
            summary_file.write_text(
                json.dumps(
                    {
                        "screen_id": "RiskScreen",
                        "overall_status": "failure",
                        "stages": {
                            "map_api": {
                                "total_transactions": 1,
                            },
                            "fidelity_audit": {
                                "risk_detected": True,
                                "missing_node_count": 1,
                                "position_style_nodes_with_risk": 1,
                            },
                            "gen_ui": {
                                "total_event_attributes": 2,
                                "runtime_wired_event_props": 1,
                                "unsupported_event_bindings": 1,
                                "behavior_actions_file": str(actions_file),
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            report_out = workspace / "prototype-acceptance.json"

            rc = main(
                [
                    "prototype-accept",
                    str(summary_file),
                    "--report-out",
                    str(report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["verdict"], "fail")
            self.assertEqual(payload["totals"]["failed_migration_count"], 1)
            self.assertEqual(payload["totals"]["fidelity_risk_count"], 1)
            self.assertEqual(payload["totals"]["unsupported_event_bindings"], 1)
            self.assertEqual(payload["totals"]["unresolved_transaction_adapter_signals"], 1)

    def test_fidelity_audit_command_fails_in_strict_mode_for_missing_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            ui_out_dir = workspace / "generated-ui"
            ui_report_out = workspace / "ui-report.json"
            fidelity_out = workspace / "fidelity-report.json"

            gen_ui_rc = main(
                [
                    "gen-ui",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(ui_out_dir),
                    "--report-out",
                    str(ui_report_out),
                    "--capture-text",
                    "--pretty",
                ]
            )
            self.assertEqual(gen_ui_rc, 0)
            ui_payload = json.loads(ui_report_out.read_text(encoding="utf-8"))
            tsx_path = Path(ui_payload["tsx_file"])
            original = tsx_path.read_text(encoding="utf-8")
            tampered = original.replace(
                'data-mi-source-node={"/Screen[1]/Contents[1]/Grid[1]"}',
                'data-mi-source-node={"__tampered__/Grid[1]"}',
                1,
            )
            self.assertNotEqual(original, tampered)
            tsx_path.write_text(tampered, encoding="utf-8")

            rc = main(
                [
                    "fidelity-audit",
                    str(FIXTURE_XML),
                    "--generated-ui-file",
                    str(tsx_path),
                    "--report-out",
                    str(fidelity_out),
                    "--strict",
                    "--capture-text",
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 2)
            self.assertTrue(fidelity_out.exists())
            payload = json.loads(fidelity_out.read_text(encoding="utf-8"))
            self.assertGreater(payload["summary"]["missing_node_count"], 0)
            self.assertIn(
                "/Screen[1]/Contents[1]/Grid[1]",
                payload["missing_node_paths"],
            )

    def test_gen_ui_generates_tsx_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-ui"
            report_out = Path(tmp_dir) / "ui-report.json"
            rc = main(
                [
                    "gen-ui",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue(report_out.exists())
            payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["screen_id"], "simple_screen_fixture")
            self.assertEqual(payload["component_name"], "SimpleScreenFixtureScreen")
            self.assertEqual(
                Path(payload["tsx_file"]).name,
                "simple-screen-fixture.tsx",
            )
            self.assertGreater(payload["summary"]["total_nodes"], 0)
            self.assertEqual(
                payload["summary"]["total_nodes"],
                payload["summary"]["rendered_nodes"],
            )

            self.assertEqual(payload["summary"]["wired_event_bindings"], 1)
            self.assertEqual(payload["summary"]["total_event_attributes"], 1)
            self.assertEqual(payload["summary"]["runtime_wired_event_props"], 1)
            self.assertEqual(payload["summary"]["unsupported_event_bindings"], 0)
            self.assertEqual(payload["unsupported_event_inventory"], [])

            tsx_path = Path(payload["tsx_file"])
            store_path = Path(payload["behavior_store_file"])
            actions_path = Path(payload["behavior_actions_file"])
            self.assertTrue(tsx_path.exists())
            self.assertTrue(store_path.exists())
            self.assertTrue(actions_path.exists())
            self.assertEqual(store_path.name, "simple-screen-fixture.store.ts")
            self.assertEqual(actions_path.name, "simple-screen-fixture.actions.ts")

            tsx_text = tsx_path.read_text(encoding="utf-8")
            self.assertIn('className="mi-widget mi-widget-button"', tsx_text)
            self.assertIn('data-mi-widget={"button"}', tsx_text)
            self.assertIn('onClick={behaviorStore.onFnSearch}', tsx_text)
            self.assertIn(
                'import { useSimpleScreenFixtureBehaviorStore } from "../behavior/simple-screen-fixture.store";',
                tsx_text,
            )
            self.assertIn(
                'data-mi-source-node={"/Screen[1]/Contents[1]/Button[1]"}',
                tsx_text,
            )
            self.assertIn("node=/Screen[1]/Contents[1]/Button[1]", tsx_text)

    def test_gen_ui_report_includes_structured_unsupported_event_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "unsupported-events.xml"
            xml_path.write_text(
                (
                    "<Screen id='UnsupportedEvents'>"
                    "<Contents>"
                    "<Button id='btnUnsupported' text='Unsupported' onclick='fnClick' onitemchanged='fnItemChanged' />"
                    "</Contents>"
                    "</Screen>"
                ),
                encoding="utf-8",
            )
            out_dir = Path(tmp_dir) / "generated-ui"
            report_out = Path(tmp_dir) / "ui-report.json"
            rc = main(
                [
                    "gen-ui",
                    str(xml_path),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            payload = json.loads(report_out.read_text(encoding="utf-8"))

            self.assertEqual(payload["summary"]["wired_event_bindings"], 2)
            self.assertEqual(payload["summary"]["total_event_attributes"], 2)
            self.assertEqual(payload["summary"]["runtime_wired_event_props"], 1)
            self.assertEqual(payload["summary"]["unsupported_event_bindings"], 1)
            self.assertEqual(len(payload["unsupported_event_inventory"]), 1)
            self.assertEqual(payload["unsupported_event_inventory"][0]["event_name"], "onitemchanged")
            self.assertEqual(
                payload["unsupported_event_inventory"][0]["reason"],
                "missing_react_event_mapping",
            )
            self.assertEqual(
                payload["unsupported_event_inventory"][0]["action_name"],
                "onFnItemChanged",
            )
            self.assertIn(
                (
                    "No React event mapping for 'onitemchanged' at "
                    "/Screen[1]/Contents[1]/Button[1]; action 'onFnItemChanged' trace emitted only."
                ),
                payload["warnings"],
            )

    def test_gen_behavior_store_generates_store_actions_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-behavior"
            report_out = Path(tmp_dir) / "behavior-store-report.json"
            rc = main(
                [
                    "gen-behavior-store",
                    str(FIXTURE_XML),
                    "--out-dir",
                    str(out_dir),
                    "--report-out",
                    str(report_out),
                    "--strict",
                    "--capture-text",
                    "--known-tags-file",
                    str(KNOWN_TAGS),
                    "--known-attrs-file",
                    str(KNOWN_ATTRS),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue(report_out.exists())
            payload = json.loads(report_out.read_text(encoding="utf-8"))

            self.assertEqual(payload["screen_id"], "simple_screen_fixture")
            self.assertEqual(payload["summary"]["generated_state_keys"], 1)
            self.assertEqual(payload["summary"]["generated_actions"], 2)
            self.assertEqual(payload["wiring_contract"]["behavior_store_hook_name"], "useSimpleScreenFixtureBehaviorStore")
            self.assertEqual(len(payload["event_action_bindings"]), 1)
            self.assertEqual(payload["event_action_bindings"][0]["action_name"], "onFnSearch")

            store_path = Path(payload["store_file"])
            actions_path = Path(payload["actions_file"])
            self.assertTrue(store_path.exists())
            self.assertTrue(actions_path.exists())
            self.assertEqual(store_path.name, "simple-screen-fixture.store.ts")
            self.assertEqual(actions_path.name, "simple-screen-fixture.actions.ts")

            store_text = store_path.read_text(encoding="utf-8")
            actions_text = actions_path.read_text(encoding="utf-8")
            self.assertIn("bindingDsOrder", store_text)
            self.assertIn("useSimpleScreenFixtureBehaviorStore", store_text)
            self.assertIn("onFnSearch", actions_text)
            self.assertIn("requestSvcOrderSearch", actions_text)
            self.assertIn("screenBehaviorEventActionBindings", actions_text)
            self.assertIn("screenBehaviorTransactionContracts", actions_text)
            self.assertIn("ScreenBehaviorTransactionAdapterHooks", actions_text)
            self.assertIn("UNIMPLEMENTED_TRANSACTION_ADAPTER", actions_text)

    def test_sync_preview_generates_manifest_registry_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            generated_dir = workspace / "generated" / "frontend" / "src" / "screens"
            preview_host_dir = workspace / "preview-host"
            manifest_path = preview_host_dir / "src" / "manifest" / "screens.manifest.json"
            registry_generated_path = (
                preview_host_dir / "src" / "screens" / "registry.generated.ts"
            )
            report_out = workspace / "preview-sync-report.json"

            generated_dir.mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "manifest").mkdir(parents=True, exist_ok=True)
            module_file = generated_dir / "Orders.tsx"
            module_file.write_text(
                "export default function Orders() { return null; }\n",
                encoding="utf-8",
            )

            rc = main(
                [
                    "sync-preview",
                    "--generated-screens-dir",
                    str(generated_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--report-out",
                    str(report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue(report_out.exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(registry_generated_path.exists())

            report_payload = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(report_payload["generated_screen_count"], 1)
            self.assertEqual(
                report_payload["generated_entry_modules"],
                ["screens/generated/Orders"],
            )

            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["schemaVersion"], "1.0")
            self.assertEqual(len(manifest_payload["screens"]), 1)
            self.assertEqual(manifest_payload["screens"][0]["screenId"], "Orders")
            self.assertEqual(
                manifest_payload["screens"][0]["entryModule"],
                "screens/generated/Orders",
            )

    def test_preview_smoke_generates_evidence_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            generated_dir = workspace / "generated" / "frontend" / "src" / "screens"
            preview_host_dir = workspace / "preview-host"
            sync_report_out = workspace / "preview-sync-report.json"
            smoke_report_out = workspace / "preview-smoke-report.json"

            generated_dir.mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "manifest").mkdir(parents=True, exist_ok=True)
            (generated_dir / "Orders.tsx").write_text(
                "export default function Orders() { return null; }\n",
                encoding="utf-8",
            )

            sync_rc = main(
                [
                    "sync-preview",
                    "--generated-screens-dir",
                    str(generated_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--report-out",
                    str(sync_report_out),
                    "--pretty",
                ]
            )
            self.assertEqual(sync_rc, 0)

            smoke_rc = main(
                [
                    "preview-smoke",
                    "--generated-screens-dir",
                    str(generated_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--report-out",
                    str(smoke_report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(smoke_rc, 0)
            payload = json.loads(smoke_report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["generated_screen_count"], 1)
            self.assertEqual(payload["route_paths"], ["/preview/Orders"])
            self.assertEqual(payload["unresolved_module_count"], 0)
            self.assertEqual(payload["screens"][0]["entry_module"], "screens/generated/Orders")
            self.assertTrue(payload["screens"][0]["route_resolvable"])

    def test_preview_smoke_returns_failure_when_modules_are_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            generated_dir = workspace / "generated" / "frontend" / "src" / "screens"
            preview_host_dir = workspace / "preview-host"
            manifest_path = preview_host_dir / "src" / "manifest" / "screens.manifest.json"
            registry_generated_path = (
                preview_host_dir / "src" / "screens" / "registry.generated.ts"
            )
            smoke_report_out = workspace / "preview-smoke-report.json"

            generated_dir.mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "manifest").mkdir(parents=True, exist_ok=True)
            (preview_host_dir / "src" / "screens").mkdir(parents=True, exist_ok=True)

            (generated_dir / "Orders.tsx").write_text(
                "export default function Orders() { return null; }\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "./screens.manifest.schema.json",
                        "schemaVersion": "1.0",
                        "generatedAtUtc": "2026-02-12T00:00:00Z",
                        "screens": [
                            {
                                "screenId": "Orders",
                                "entryModule": "screens/generated/Orders",
                                "sourceXmlPath": "generated/frontend/src/screens/Orders.tsx",
                                "sourceNodePath": "/generated/screens/Orders",
                            },
                            {
                                "screenId": "Missing",
                                "entryModule": "screens/generated/Missing",
                                "sourceXmlPath": "generated/frontend/src/screens/Missing.tsx",
                                "sourceNodePath": "/generated/screens/Missing",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            registry_generated_path.write_text(
                "\n".join(
                    [
                        "/* Auto-generated */",
                        'import type { ScreenModuleLoader } from "../manifest/types";',
                        "",
                        "export const generatedScreenModuleLoaders: Record<string, ScreenModuleLoader> = {",
                        '  "screens/generated/Orders": () => import("../../../generated/frontend/src/screens/Orders"),',
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            smoke_rc = main(
                [
                    "preview-smoke",
                    "--generated-screens-dir",
                    str(generated_dir),
                    "--preview-host-dir",
                    str(preview_host_dir),
                    "--report-out",
                    str(smoke_report_out),
                    "--pretty",
                ]
            )

            self.assertEqual(smoke_rc, 2)
            payload = json.loads(smoke_report_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["unresolved_module_count"], 1)
            unresolved = next(item for item in payload["screens"] if item["screen_id"] == "Missing")
            self.assertFalse(unresolved["route_resolvable"])

    def test_desktop_shell_command_dispatches_launcher(self) -> None:
        with mock.patch("migrator.cli.run_desktop_shell", return_value=0) as launcher:
            rc = main(["desktop-shell", "--no-event-loop"])

        self.assertEqual(rc, 0)
        launcher.assert_called_once()
        args = launcher.call_args.args[0]
        self.assertTrue(args.no_event_loop)


if __name__ == "__main__":
    unittest.main()
