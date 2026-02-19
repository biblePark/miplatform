from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.runner_service import RunnerService  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"


def _write_success_summary(args: object) -> int:
    xml_path = Path(str(getattr(args, "xml_path")))
    out_dir = Path(str(getattr(args, "out_dir")))
    summary_out = getattr(args, "summary_out", None)
    summary_path = (
        Path(summary_out)
        if isinstance(summary_out, str) and summary_out
        else (out_dir / f"{xml_path.stem}.migration-summary.json")
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "overall_status": "success",
                "overall_exit_code": 0,
                "reports": {"consolidated_summary": str(summary_path)},
                "stages": {"parse": {"status": "success", "exit_code": 0}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return 0


class TestRunnerService(unittest.TestCase):
    def _wait_terminal(self, service: RunnerService, job_id: str, *, timeout_seconds: float = 10.0) -> dict[str, object]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            job = service.get_job(job_id)
            status = job["status"]
            self.assertIn(status, {"queued", "running", "succeeded", "failed", "canceled"})
            if status in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(0.05)
        self.fail(f"Job did not reach terminal state: {job_id}")

    def test_schedule_batch_queues_jobs_and_emits_batch_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            hook_calls: list[tuple[str, tuple[str, ...]]] = []
            service = RunnerService(
                workspace_root=ROOT,
                job_store_path=tmp_root / "jobs.json",
                pipeline_runner=_write_success_summary,
                batch_scheduled_hook=lambda batch_id, job_ids: hook_calls.append((batch_id, job_ids)),
            )
            try:
                payloads = []
                for idx in range(2):
                    job_root = tmp_root / f"job-{idx}"
                    payloads.append(
                        {
                            "xml_path": str(FIXTURE_XML),
                            "out_dir": str(job_root / "out"),
                            "api_out_dir": str(job_root / "generated-api"),
                            "ui_out_dir": str(job_root / "generated-ui"),
                            "preview_host_dir": str(ROOT / "preview-host"),
                            "use_isolated_preview_host": False,
                        }
                    )

                batch = service.schedule_batch(payloads, batch_id="batch-r13")
                self.assertEqual(batch["batch_id"], "batch-r13")
                self.assertEqual(batch["total"], 2)
                self.assertEqual(len(batch["jobs"]), 2)

                job_ids = [job["id"] for job in batch["jobs"]]
                for job_id in job_ids:
                    terminal = self._wait_terminal(service, job_id)
                    self.assertEqual(terminal["status"], "succeeded")
                    logs = service.get_job_logs(job_id)["logs"]
                    events = [entry["event"] for entry in logs]
                    self.assertIn("batch_scheduled", events)

                self.assertEqual(len(hook_calls), 1)
                self.assertEqual(hook_calls[0][0], "batch-r13")
                self.assertEqual(list(hook_calls[0][1]), job_ids)
            finally:
                service.shutdown()

    def test_cooperative_cancel_hook_cancels_before_pipeline_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            run_calls = 0

            def _counting_runner(args: object) -> int:
                nonlocal run_calls
                run_calls += 1
                return _write_success_summary(args)

            service = RunnerService(
                workspace_root=ROOT,
                job_store_path=tmp_root / "jobs.json",
                pipeline_runner=_counting_runner,
                cooperative_cancel_hook=lambda _job_id, _request: True,
            )
            try:
                job = service.create_job(
                    {
                        "xml_path": str(FIXTURE_XML),
                        "out_dir": str(tmp_root / "out"),
                        "api_out_dir": str(tmp_root / "generated-api"),
                        "ui_out_dir": str(tmp_root / "generated-ui"),
                        "preview_host_dir": str(ROOT / "preview-host"),
                        "use_isolated_preview_host": False,
                    }
                )

                terminal = self._wait_terminal(service, str(job["id"]))
                self.assertEqual(terminal["status"], "canceled")
                self.assertEqual(run_calls, 0)

                logs = service.get_job_logs(str(job["id"]))["logs"]
                events = [entry["event"] for entry in logs]
                self.assertIn("cancel_requested", events)
                self.assertIn("job_canceled", events)
            finally:
                service.shutdown()


if __name__ == "__main__":
    unittest.main()
