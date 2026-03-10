from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator import orchestrator_api as orchestrator_api_module  # noqa: E402
from migrator.orchestrator_api import OrchestratorJobRequest, OrchestratorService  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"
KNOWN_TAGS = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS = FIXTURES_DIR / "known_attrs_all.json"


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
                "reports": {
                    "consolidated_summary": str(summary_path),
                },
                "stages": {
                    "parse": {"status": "success", "exit_code": 0},
                    "map_api": {"status": "success", "exit_code": 0},
                    "gen_ui": {"status": "success", "exit_code": 0},
                    "fidelity_audit": {"status": "success", "exit_code": 0},
                    "sync_preview": {"status": "success", "exit_code": 0},
                    "preview_smoke": {"status": "success", "exit_code": 0},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return 0


class TestRunnerServiceContract(unittest.TestCase):
    def setUp(self) -> None:
        self._job_store_dir = tempfile.TemporaryDirectory()
        self.job_store_path = Path(self._job_store_dir.name) / "jobs.json"
        self.service = OrchestratorService(
            workspace_root=ROOT,
            job_store_path=self.job_store_path,
        )

    def tearDown(self) -> None:
        self.service.shutdown()
        self._job_store_dir.cleanup()

    def _wait_terminal(self, job_id: str, timeout_seconds: float = 20.0) -> dict[str, object]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            job = self.service.get_job(job_id)
            self.assertIsInstance(job, dict)
            status = job["status"]
            self.assertIn(status, {"queued", "running", "succeeded", "failed", "canceled"})
            if status in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(0.05)
        self.fail(f"Job did not reach terminal state in {timeout_seconds} seconds: {job_id}")

    def _wait_running(self, job_id: str, timeout_seconds: float = 20.0) -> dict[str, object]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            job = self.service.get_job(job_id)
            self.assertIsInstance(job, dict)
            status = job["status"]
            if status == "running":
                return job
            if status in {"succeeded", "failed", "canceled"}:
                self.fail(f"Job reached terminal state before running: {status}")
            time.sleep(0.05)
        self.fail(f"Job did not reach running state in {timeout_seconds} seconds: {job_id}")

    def test_job_request_contract_exposes_cli_namespace_and_public_fields(self) -> None:
        request = OrchestratorJobRequest(
            xml_path=str(FIXTURE_XML),
            out_dir=str(ROOT / "out"),
            api_out_dir=str(ROOT / "generated" / "api"),
            ui_out_dir=str(ROOT / "generated" / "frontend"),
            preview_host_dir=str(ROOT / "preview-host"),
            summary_out=None,
            parse_report_out=None,
            map_report_out=None,
            ui_report_out=None,
            fidelity_report_out=None,
            preview_report_out=None,
            manifest_file=None,
            registry_generated_file=None,
            known_tags_file=str(KNOWN_TAGS),
            known_attrs_file=str(KNOWN_ATTRS),
            strict=True,
            capture_text=True,
            disable_roundtrip_gate=False,
            roundtrip_mismatch_limit=200,
            render_policy_mode="auto",
            auto_risk_threshold=0.2,
            include_render_mode="component",
            pretty=True,
            use_isolated_preview_host=True,
            preview_host_source_dir=str(ROOT / "preview-host"),
        )

        namespace = request.to_cli_namespace()
        self.assertEqual(namespace.xml_path, request.xml_path)
        self.assertEqual(namespace.out_dir, request.out_dir)
        self.assertEqual(namespace.preview_host_dir, request.preview_host_dir)
        self.assertEqual(namespace.render_policy_mode, "auto")
        self.assertEqual(namespace.auto_risk_threshold, 0.2)
        self.assertEqual(namespace.include_render_mode, "component")

        public = request.to_public_dict()
        self.assertTrue(public["use_isolated_preview_host"])
        self.assertEqual(public["preview_host_source_dir"], str(ROOT / "preview-host"))
        self.assertEqual(public["roundtrip_mismatch_limit"], 200)
        self.assertEqual(public["include_render_mode"], "component")

    def test_service_executes_job_and_surfaces_preview_stage_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            payload = {
                "xml_path": str(FIXTURE_XML),
                "out_dir": str(workspace / "out-e2e"),
                "api_out_dir": str(workspace / "generated-api"),
                "ui_out_dir": str(workspace / "generated-ui"),
                "known_tags_file": str(KNOWN_TAGS),
                "known_attrs_file": str(KNOWN_ATTRS),
                "preview_host_source_dir": str(ROOT / "preview-host"),
                "use_isolated_preview_host": True,
                "render_policy_mode": "auto",
                "pretty": True,
            }

            with mock.patch.object(orchestrator_api_module, "run_migrate_e2e", side_effect=_write_success_summary):
                created = self.service.create_job(payload)
                job_id = created["id"]
                terminal = self._wait_terminal(job_id)

            self.assertEqual(terminal["status"], "succeeded")
            artifacts = self.service.get_job_artifacts(job_id)
            self.assertEqual(artifacts["artifacts"]["overall_status"], "success")
            self.assertIn("preview_smoke", artifacts["artifacts"]["stages"])

    def test_service_cancel_contract_marks_running_job_as_canceled(self) -> None:
        release = threading.Event()

        def _blocking_run(args: object) -> int:
            release.wait(timeout=10)
            return _write_success_summary(args)

        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            payload = {
                "xml_path": str(FIXTURE_XML),
                "out_dir": str(workspace / "out-e2e"),
                "api_out_dir": str(workspace / "generated-api"),
                "ui_out_dir": str(workspace / "generated-ui"),
                "preview_host_dir": str(ROOT / "preview-host"),
                "use_isolated_preview_host": False,
            }

            with mock.patch.object(orchestrator_api_module, "run_migrate_e2e", side_effect=_blocking_run):
                created = self.service.create_job(payload)
                job_id = created["id"]
                running_job = self._wait_running(job_id)
                self.assertFalse(running_job["cancel_requested"])

                canceled = self.service.cancel_job(job_id)
                self.assertTrue(canceled["cancel_requested"])
                release.set()
                terminal = self._wait_terminal(job_id)

            self.assertEqual(terminal["status"], "canceled")


if __name__ == "__main__":
    unittest.main()
