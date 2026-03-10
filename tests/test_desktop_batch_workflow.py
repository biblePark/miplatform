from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.desktop_batch_workflow import (  # noqa: E402
    BatchRunItemResult,
    build_batch_run_id,
    build_batch_run_plan,
    build_batch_run_plan_from_xml_queue,
    build_batch_summary_view,
    build_failure_retry_plan,
    build_project_workspace_layout,
    consolidate_batch_run_artifacts,
    read_project_coverage_ledger,
    read_project_manifest,
    list_batch_run_history,
    materialize_batch_run_layout,
    read_batch_run_plan,
    read_batch_summary_view,
    resolve_source_xml_queue,
    write_batch_summary_view,
)


class TestDesktopBatchWorkflow(unittest.TestCase):
    def test_build_batch_run_plan_from_folder_resolves_queue_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            source_dir = workspace / "xml"
            (source_dir / "nested").mkdir(parents=True, exist_ok=True)

            first = source_dir / "a.xml"
            second = source_dir / "nested" / "b.xml"
            ignored = source_dir / "nested" / "ignore.txt"

            first.write_text("<Screen id='A' />", encoding="utf-8")
            second.write_text("<Screen id='B' />", encoding="utf-8")
            ignored.write_text("<Screen id='Ignore' />", encoding="utf-8")

            output_root = workspace / "out"
            plan = build_batch_run_plan(
                output_root_dir=output_root,
                source_xml_dir=source_dir,
                recursive=True,
                glob_pattern="*.xml",
                run_id="r13-folder-plan",
                generated_at_utc="2026-02-19T00:00:00+00:00",
            )

            self.assertEqual(plan.run_id, "r13-folder-plan")
            self.assertEqual(plan.summary.total_items, 2)
            self.assertEqual(plan.summary.source_mode, "folder")
            self.assertEqual(plan.output.project_key, "out")
            self.assertTrue(plan.output.project_manifest_file is not None)
            self.assertEqual(
                [item.xml_path for item in plan.items],
                [str(first.resolve()), str(second.resolve())],
            )
            self.assertTrue(plan.output.run_root_dir.endswith("desktop-runs/r13-folder-plan"))

            run_root = materialize_batch_run_layout(
                plan,
                write_plan_manifest=True,
                write_queued_summary=True,
            )
            self.assertTrue(run_root.exists())
            self.assertTrue((run_root / "batch-run-plan.json").exists())
            self.assertTrue((run_root / "batch-run-summary.json").exists())
            self.assertTrue(Path(plan.items[0].output.out_dir).exists())
            self.assertTrue(Path(plan.items[0].output.api_out_dir).exists())
            self.assertTrue(Path(plan.items[0].output.ui_out_dir).exists())
            self.assertTrue(Path(plan.items[0].output.preview_host_dir).exists())

            payload = json.loads((run_root / "batch-run-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_items"], 2)
            self.assertEqual(payload["selection"]["glob_pattern"], "*.xml")

    def test_summary_view_and_failure_only_retry_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_a = workspace / "a.xml"
            xml_b = workspace / "b.xml"
            xml_c = workspace / "c.xml"
            xml_a.write_text("<Screen id='A' />", encoding="utf-8")
            xml_b.write_text("<Screen id='B' />", encoding="utf-8")
            xml_c.write_text("<Screen id='C' />", encoding="utf-8")

            plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_a, xml_b, xml_c],
                output_root_dir=workspace / "out",
                run_id="primary-run",
                generated_at_utc="2026-02-19T00:00:00+00:00",
            )
            results = [
                BatchRunItemResult(
                    queue_index=1,
                    xml_path=str(xml_a),
                    status="succeeded",
                    exit_code=0,
                ),
                BatchRunItemResult(
                    queue_index=2,
                    xml_path=str(xml_b),
                    status="failed",
                    exit_code=2,
                    error_message="pipeline_failed",
                ),
                BatchRunItemResult(
                    queue_index=3,
                    xml_path=str(xml_c),
                    status="canceled",
                ),
            ]
            summary = build_batch_summary_view(plan, item_results=results)

            self.assertEqual(summary.total_items, 3)
            self.assertEqual(summary.succeeded_count, 1)
            self.assertEqual(summary.failed_count, 1)
            self.assertEqual(summary.canceled_count, 1)
            self.assertEqual(summary.retryable_failed_count, 1)

            failed_items = [item for item in summary.items if item.status == "failed"]
            self.assertEqual(len(failed_items), 1)
            self.assertTrue(failed_items[0].is_retry_candidate)
            self.assertEqual(failed_items[0].xml_path, str(xml_b.resolve()))

            retry_plan = build_failure_retry_plan(
                summary,
                run_id="retry-run",
                generated_at_utc="2026-02-19T00:01:00+00:00",
            )
            self.assertEqual(retry_plan.retry_of_run_id, "primary-run")
            self.assertEqual(retry_plan.summary.source_mode, "explicit_queue")
            self.assertEqual(retry_plan.summary.total_items, 1)
            self.assertEqual(retry_plan.items[0].xml_path, str(xml_b.resolve()))

    def test_resolve_source_xml_queue_requires_exactly_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_path = workspace / "screen.xml"
            xml_path.write_text("<Screen id='A' />", encoding="utf-8")
            folder_path = workspace / "xml"
            folder_path.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(ValueError):
                resolve_source_xml_queue()
            with self.assertRaises(ValueError):
                resolve_source_xml_queue(
                    source_xml_file=xml_path,
                    source_xml_dir=folder_path,
                )

    def test_build_batch_run_id_is_deterministic_for_same_queue_and_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_a = workspace / "a.xml"
            xml_b = workspace / "b.xml"
            xml_a.write_text("<Screen id='A' />", encoding="utf-8")
            xml_b.write_text("<Screen id='B' />", encoding="utf-8")

            queue = [xml_a, xml_b]
            first = build_batch_run_id(
                queue,
                generated_at_utc="2026-02-19T12:00:00+00:00",
            )
            second = build_batch_run_id(
                queue,
                generated_at_utc="2026-02-19T12:00:00+00:00",
            )
            self.assertEqual(first, second)

    def test_history_listing_and_contract_readers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            output_root = workspace / "out"
            xml_a = workspace / "a.xml"
            xml_b = workspace / "b.xml"
            xml_a.write_text("<Screen id='A' />", encoding="utf-8")
            xml_b.write_text("<Screen id='B' />", encoding="utf-8")

            first_plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_a],
                output_root_dir=output_root,
                run_id="run-old",
                generated_at_utc="2026-02-20T00:00:00+00:00",
            )
            materialize_batch_run_layout(
                first_plan,
                write_plan_manifest=True,
                write_queued_summary=False,
            )
            first_summary = build_batch_summary_view(
                first_plan,
                item_results=[
                    BatchRunItemResult(
                        queue_index=1,
                        xml_path=str(xml_a),
                        status="succeeded",
                        exit_code=0,
                    )
                ],
                generated_at_utc="2026-02-20T00:01:00+00:00",
            )
            write_batch_summary_view(first_summary, output_path=first_plan.output.summary_file)

            second_plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_b],
                output_root_dir=output_root,
                run_id="run-new",
                generated_at_utc="2026-02-20T01:00:00+00:00",
            )
            materialize_batch_run_layout(
                second_plan,
                write_plan_manifest=True,
                write_queued_summary=False,
            )
            second_summary = build_batch_summary_view(
                second_plan,
                item_results=[
                    BatchRunItemResult(
                        queue_index=1,
                        xml_path=str(xml_b),
                        status="failed",
                        exit_code=2,
                        error_message="pipeline_failed",
                    )
                ],
                generated_at_utc="2026-02-20T01:01:00+00:00",
            )
            write_batch_summary_view(second_summary, output_path=second_plan.output.summary_file)

            loaded_plan = read_batch_run_plan(first_plan.output.run_root_dir)
            loaded_summary = read_batch_summary_view(first_plan.output.summary_file)
            self.assertEqual(loaded_plan.run_id, "run-old")
            self.assertEqual(len(loaded_plan.items), 1)
            self.assertEqual(loaded_summary.run_id, "run-old")
            self.assertEqual(loaded_summary.succeeded_count, 1)

            history = list_batch_run_history(output_root, limit=10)
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0].run_id, "run-new")
            self.assertEqual(history[1].run_id, "run-old")
            self.assertEqual(history[0].failed_count, 1)
            self.assertTrue(history[0].summary_file.endswith("batch-run-summary.json"))
            self.assertTrue(history[0].plan_file is not None)

    def test_consolidate_batch_run_artifacts_updates_project_manifest_and_copies_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            output_root = workspace / "out"
            xml_a = workspace / "a.xml"
            xml_b = workspace / "b.xml"
            xml_a.write_text("<Form id='A' />", encoding="utf-8")
            xml_b.write_text("<Form id='B' />", encoding="utf-8")

            plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_a, xml_b],
                output_root_dir=output_root,
                run_id="run-consolidate",
                generated_at_utc="2026-02-23T01:00:00+00:00",
            )
            materialize_batch_run_layout(plan, write_plan_manifest=True, write_queued_summary=False)

            results: list[BatchRunItemResult] = []
            for item in plan.items:
                ui_screen = Path(item.output.ui_out_dir) / "src" / "screens" / f"{item.xml_stem}.tsx"
                api_route = Path(item.output.api_out_dir) / "src" / "routes" / f"{item.xml_stem}.route.js"
                ui_screen.parent.mkdir(parents=True, exist_ok=True)
                api_route.parent.mkdir(parents=True, exist_ok=True)
                ui_screen.write_text(f"export default function {item.xml_stem}() {{ return null; }}", encoding="utf-8")
                api_route.write_text("export const route = {}; ", encoding="utf-8")

                parse_report = Path(item.output.out_dir) / f"{item.xml_stem}.parse-report.json"
                parse_report.parent.mkdir(parents=True, exist_ok=True)
                parse_report.write_text('{"stage":"parse"}', encoding="utf-8")

                summary_payload = {
                    "overall_status": "success",
                    "overall_exit_code": 0,
                    "reports": {
                        "parse_report": str(parse_report.resolve()),
                        "consolidated_summary": str(Path(item.output.summary_out).resolve()),
                    },
                    "stages": {
                        "parse": {"status": "success"},
                    },
                }
                Path(item.output.summary_out).parent.mkdir(parents=True, exist_ok=True)
                Path(item.output.summary_out).write_text(
                    json.dumps(summary_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                results.append(
                    BatchRunItemResult(
                        queue_index=item.queue_index,
                        xml_path=item.xml_path,
                        status="succeeded",
                        exit_code=0,
                        summary_file=item.output.summary_out,
                    )
                )

            summary = build_batch_summary_view(
                plan,
                item_results=results,
                generated_at_utc="2026-02-23T01:01:00+00:00",
            )
            write_batch_summary_view(summary, output_path=plan.output.summary_file)
            consolidation = consolidate_batch_run_artifacts(plan, summary, pretty=True)

            project_layout = build_project_workspace_layout(output_root, project_key=plan.output.project_key)
            manifest = read_project_manifest(project_layout.project_root_dir)

            self.assertEqual(consolidation.project_key, plan.output.project_key)
            self.assertGreater(consolidation.copied_count, 0)
            self.assertTrue(Path(consolidation.consolidation_report_file).exists())
            self.assertTrue(consolidation.coverage_ledger_file is not None)
            self.assertTrue(Path(str(consolidation.coverage_ledger_file)).exists())
            self.assertTrue(Path(project_layout.manifest_file).exists())
            self.assertEqual(manifest.run_count, 1)
            self.assertEqual(manifest.latest_run_id, "run-consolidate")
            self.assertTrue(manifest.last_coverage_ledger_file is not None)
            self.assertTrue(
                (Path(project_layout.frontend_artifacts_dir) / "src" / "screens" / "a.tsx").exists()
            )
            self.assertTrue(
                (Path(project_layout.api_artifacts_dir) / "src" / "routes" / "b.route.js").exists()
            )

    def test_consolidation_collision_renames_target_and_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            output_root = workspace / "out"
            xml_a = workspace / "a.xml"
            xml_a.write_text("<Form id='A' />", encoding="utf-8")

            first_plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_a],
                output_root_dir=output_root,
                run_id="run-first",
                generated_at_utc="2026-02-23T02:00:00+00:00",
            )
            materialize_batch_run_layout(first_plan, write_plan_manifest=True, write_queued_summary=False)
            first_item = first_plan.items[0]
            first_ui_file = Path(first_item.output.ui_out_dir) / "src" / "screens" / "a.tsx"
            first_ui_file.parent.mkdir(parents=True, exist_ok=True)
            first_ui_file.write_text("export const v = 'first';", encoding="utf-8")
            Path(first_item.output.summary_out).parent.mkdir(parents=True, exist_ok=True)
            Path(first_item.output.summary_out).write_text(
                json.dumps({"reports": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            first_summary = build_batch_summary_view(
                first_plan,
                item_results=[
                    BatchRunItemResult(
                        queue_index=1,
                        xml_path=first_item.xml_path,
                        status="succeeded",
                        summary_file=first_item.output.summary_out,
                    )
                ],
                generated_at_utc="2026-02-23T02:01:00+00:00",
            )
            write_batch_summary_view(first_summary, output_path=first_plan.output.summary_file)
            consolidate_batch_run_artifacts(first_plan, first_summary, pretty=True)

            second_plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_a],
                output_root_dir=output_root,
                run_id="run-second",
                generated_at_utc="2026-02-23T03:00:00+00:00",
                project_key=first_plan.output.project_key,
            )
            materialize_batch_run_layout(second_plan, write_plan_manifest=True, write_queued_summary=False)
            second_item = second_plan.items[0]
            second_ui_file = Path(second_item.output.ui_out_dir) / "src" / "screens" / "a.tsx"
            second_ui_file.parent.mkdir(parents=True, exist_ok=True)
            second_ui_file.write_text("export const v = 'second';", encoding="utf-8")
            Path(second_item.output.summary_out).parent.mkdir(parents=True, exist_ok=True)
            Path(second_item.output.summary_out).write_text(
                json.dumps({"reports": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            second_summary = build_batch_summary_view(
                second_plan,
                item_results=[
                    BatchRunItemResult(
                        queue_index=1,
                        xml_path=second_item.xml_path,
                        status="succeeded",
                        summary_file=second_item.output.summary_out,
                    )
                ],
                generated_at_utc="2026-02-23T03:01:00+00:00",
            )
            write_batch_summary_view(second_summary, output_path=second_plan.output.summary_file)
            second_report = consolidate_batch_run_artifacts(second_plan, second_summary, pretty=True)

            project_layout = build_project_workspace_layout(output_root, project_key=second_plan.output.project_key)
            merged_screen_dir = Path(project_layout.frontend_artifacts_dir) / "src" / "screens"
            self.assertTrue((merged_screen_dir / "a.tsx").exists())
            self.assertTrue((merged_screen_dir / "a__run-second.tsx").exists())
            self.assertGreaterEqual(second_report.collision_renamed_count, 1)

            manifest = read_project_manifest(project_layout.project_root_dir)
            self.assertEqual(manifest.run_count, 2)
            self.assertEqual(manifest.latest_run_id, "run-second")
            self.assertGreaterEqual(len(manifest.recent_collisions), 1)

    def test_consolidation_writes_coverage_ledger_with_parse_and_codegen_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            output_root = workspace / "out"
            xml_file = workspace / "sample.xml"
            xml_file.write_text("<Form id='A' />", encoding="utf-8")

            plan = build_batch_run_plan_from_xml_queue(
                xml_queue=[xml_file],
                output_root_dir=output_root,
                run_id="run-coverage",
                generated_at_utc="2026-02-23T11:00:00+00:00",
            )
            materialize_batch_run_layout(plan, write_plan_manifest=True, write_queued_summary=False)
            item = plan.items[0]

            parse_report = Path(item.output.out_dir) / f"{item.xml_stem}.parse-report.json"
            gen_ui_report = Path(item.output.out_dir) / f"{item.xml_stem}.gen-ui-report.json"
            parse_report.parent.mkdir(parents=True, exist_ok=True)
            parse_report.write_text(
                json.dumps(
                    {
                        "stats": {
                            "total_nodes": 11,
                            "unknown_tags": [{"tag": "XChart", "node_path": "/Form[1]/XChart[1]"}],
                            "unknown_attrs": [
                                {
                                    "tag": "Button",
                                    "attr": "legacyAttr",
                                    "node_path": "/Form[1]/Button[1]",
                                }
                            ],
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            gen_ui_report.write_text(
                json.dumps(
                    {
                        "summary": {
                            "total_nodes": 9,
                            "rendered_nodes": 8,
                            "unsupported_event_bindings": 2,
                        },
                        "warnings": [
                            "Unsupported tag: XChart",
                            "Unsupported tag: _PersistData",
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            Path(item.output.summary_out).parent.mkdir(parents=True, exist_ok=True)
            Path(item.output.summary_out).write_text(
                json.dumps(
                    {
                        "reports": {
                            "parse_report": str(parse_report.resolve()),
                            "gen_ui_report": str(gen_ui_report.resolve()),
                            "consolidated_summary": str(Path(item.output.summary_out).resolve()),
                        },
                        "stages": {
                            "gen_ui": {
                                "total_nodes": 9,
                                "rendered_nodes": 8,
                                "unsupported_event_bindings": 2,
                            }
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            summary = build_batch_summary_view(
                plan,
                item_results=[
                    BatchRunItemResult(
                        queue_index=1,
                        xml_path=item.xml_path,
                        status="succeeded",
                        summary_file=item.output.summary_out,
                    )
                ],
                generated_at_utc="2026-02-23T11:01:00+00:00",
            )
            write_batch_summary_view(summary, output_path=plan.output.summary_file)
            report = consolidate_batch_run_artifacts(plan, summary, pretty=True)

            ledger_file = Path(str(report.coverage_ledger_file))
            self.assertTrue(ledger_file.exists())
            ledger = read_project_coverage_ledger(ledger_file)
            self.assertEqual(ledger.total_runs, 1)
            self.assertEqual(ledger.project_key, plan.output.project_key)
            ledger_payload = json.loads(ledger_file.read_text(encoding="utf-8"))
            self.assertEqual(ledger_payload["project_key"], plan.output.project_key)
            self.assertEqual(ledger_payload["total_runs"], 1)
            self.assertEqual(ledger_payload["parse_total_nodes"], 11)
            self.assertEqual(ledger_payload["parse_unknown_tag_count"], 1)
            self.assertEqual(ledger_payload["parse_unknown_attr_count"], 1)
            self.assertEqual(ledger_payload["ui_total_nodes"], 9)
            self.assertEqual(ledger_payload["ui_rendered_nodes"], 8)
            self.assertEqual(ledger_payload["ui_unsupported_event_bindings"], 2)
            self.assertEqual(ledger_payload["ui_unsupported_tag_warning_count"], 2)
            self.assertIn("XChart", ledger_payload["unique_unknown_tags"])
            self.assertIn("Button.legacyAttr", ledger_payload["unique_unknown_attrs"])
            self.assertIn("XChart", ledger_payload["unique_ui_unsupported_tags"])

    def test_list_batch_run_history_reads_project_runs_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            output_root = workspace / "out"
            project_runs_root = output_root / "projects" / "demo-project" / "runs" / "run-1"
            project_runs_root.mkdir(parents=True, exist_ok=True)

            payload = {
                "contract_version": 1,
                "run_id": "run-1",
                "retry_of_run_id": None,
                "generated_at_utc": "2026-02-23T10:00:00+00:00",
                "output_root_dir": str(output_root.resolve()),
                "run_root_dir": str(project_runs_root.resolve()),
                "total_items": 1,
                "queued_count": 0,
                "running_count": 0,
                "succeeded_count": 1,
                "failed_count": 0,
                "canceled_count": 0,
                "skipped_count": 0,
                "retryable_failed_count": 0,
                "project_key": "demo-project",
                "project_root_dir": str((output_root / "projects" / "demo-project").resolve()),
                "project_manifest_file": str(
                    (output_root / "projects" / "demo-project" / "project.json").resolve()
                ),
                "items": [
                    {
                        "queue_index": 1,
                        "xml_path": str((workspace / "a.xml").resolve()),
                        "xml_stem": "a",
                        "status": "succeeded",
                        "exit_code": 0,
                        "summary_file": str((project_runs_root / "a.migration-summary.json").resolve()),
                        "error_message": None,
                        "item_root_dir": str((project_runs_root / "items" / "0001-a").resolve()),
                        "summary_out": str((project_runs_root / "a.migration-summary.json").resolve()),
                        "is_retry_candidate": False,
                    }
                ],
            }
            (project_runs_root / "batch-run-summary.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project_runs_root / "batch-run-plan.json").write_text("{}", encoding="utf-8")

            history = list_batch_run_history(output_root, limit=10)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].run_id, "run-1")
            self.assertEqual(history[0].project_key, "demo-project")
            self.assertTrue(history[0].run_root_dir.endswith("/projects/demo-project/runs/run-1"))


if __name__ == "__main__":
    unittest.main()
