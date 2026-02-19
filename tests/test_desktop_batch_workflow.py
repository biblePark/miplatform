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
    materialize_batch_run_layout,
    resolve_source_xml_queue,
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


if __name__ == "__main__":
    unittest.main()
