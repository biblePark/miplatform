from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.cli import run_migrate_e2e as run_migrate_e2e_cli  # noqa: E402
from migrator import orchestrator_api as orchestrator_api_module  # noqa: E402
from migrator.orchestrator_api import create_orchestrator_http_server  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"
KNOWN_TAGS = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS = FIXTURES_DIR / "known_attrs_all.json"


def _run_migrate_e2e_with_default_auto_threshold(args: object) -> int:
    if not hasattr(args, "auto_risk_threshold"):
        setattr(args, "auto_risk_threshold", None)
    return run_migrate_e2e_cli(args)  # type: ignore[arg-type]


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


def _http_json(
    *,
    base_url: str,
    method: str,
    path: str,
    payload: object | None = None,
) -> tuple[int, dict[str, object]]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib_request.Request(
        url=f"{base_url}{path}",
        data=data,
        method=method,
        headers=headers,
    )

    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw)


class TestOrchestratorApi(unittest.TestCase):
    def setUp(self) -> None:
        self._run_migrate_patch = mock.patch.object(
            orchestrator_api_module,
            "run_migrate_e2e",
            side_effect=_run_migrate_e2e_with_default_auto_threshold,
        )
        self._run_migrate_patch.start()
        self._job_store_dir = tempfile.TemporaryDirectory()
        self.job_store_path = Path(self._job_store_dir.name) / "jobs.json"
        self.server = None
        self.thread = None
        self.base_url = ""
        self._start_server()

    def tearDown(self) -> None:
        self._stop_server()
        self._job_store_dir.cleanup()
        self._run_migrate_patch.stop()

    def _start_server(self) -> None:
        self.server = create_orchestrator_http_server(
            host="127.0.0.1",
            port=0,
            workspace_root=ROOT,
            job_store_path=self.job_store_path,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def _stop_server(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.server = None
        self.thread = None

    def _restart_server(self) -> None:
        self._stop_server()
        self._start_server()

    def _wait_status(self, job_id: str, *, expected_status: str, timeout_seconds: float = 30.0) -> dict[str, object]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            status_code, payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}",
            )
            self.assertEqual(status_code, 200)
            job = payload["job"]
            self.assertIsInstance(job, dict)
            if job["status"] == expected_status:
                return job
            time.sleep(0.05)
        self.fail(f"Job did not reach expected status in {timeout_seconds} seconds: {job_id} -> {expected_status}")

    def _wait_terminal(self, job_id: str, *, timeout_seconds: float = 30.0) -> dict[str, object]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            status_code, payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}",
            )
            self.assertEqual(status_code, 200)
            job = payload["job"]
            self.assertIsInstance(job, dict)
            current_status = job["status"]
            self.assertIn(current_status, {"queued", "running", "succeeded", "failed", "canceled"})
            if current_status in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(0.1)
        self.fail(f"Job did not reach terminal state in {timeout_seconds} seconds: {job_id}")

    def test_health_endpoint(self) -> None:
        status_code, payload = _http_json(
            base_url=self.base_url,
            method="GET",
            path="/health",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "mifl-migrator-orchestrator-api")
        self.assertIn("time_utc", payload)

    def test_post_jobs_runs_pipeline_and_exposes_logs_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            out_dir = workspace / "out-e2e"
            api_out_dir = workspace / "generated-api"
            ui_out_dir = workspace / "generated-ui"

            status_code, payload = _http_json(
                base_url=self.base_url,
                method="POST",
                path="/jobs",
                payload={
                    "xml_path": str(FIXTURE_XML),
                    "out_dir": str(out_dir),
                    "api_out_dir": str(api_out_dir),
                    "ui_out_dir": str(ui_out_dir),
                    "known_tags_file": str(KNOWN_TAGS),
                    "known_attrs_file": str(KNOWN_ATTRS),
                    "strict": True,
                    "capture_text": True,
                    "pretty": True,
                    "use_isolated_preview_host": True,
                },
            )
            self.assertEqual(status_code, 202)
            created_job = payload["job"]
            self.assertIn(created_job["status"], {"queued", "running"})

            job_id = created_job["id"]
            completed = self._wait_terminal(job_id)
            self.assertEqual(completed["status"], "succeeded")
            self.assertEqual(completed["result"]["exit_code"], 0)
            self.assertEqual(completed["result"]["summary_overview"]["overall_status"], "success")

            status_code, log_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}/logs",
            )
            self.assertEqual(status_code, 200)
            events = [entry["event"] for entry in log_payload["logs"]]
            self.assertIn("job_queued", events)
            self.assertIn("pipeline_started", events)
            self.assertIn("job_finished", events)

            status_code, artifacts_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}/artifacts",
            )
            self.assertEqual(status_code, 200)
            artifacts = artifacts_payload["artifacts"]
            self.assertEqual(artifacts["overall_status"], "success")
            stages = artifacts["stages"]
            self.assertIn("parse", stages)
            self.assertIn("map_api", stages)
            self.assertIn("gen_ui", stages)
            self.assertIn("fidelity_audit", stages)
            self.assertIn("sync_preview", stages)
            self.assertIn("preview_smoke", stages)

            reports = artifacts["reports"]
            self.assertTrue(Path(reports["consolidated_summary"]).exists())
            self.assertTrue(Path(reports["parse_report"]).exists())
            self.assertTrue(Path(reports["map_api_report"]).exists())
            self.assertTrue(Path(reports["gen_ui_report"]).exists())
            self.assertTrue(Path(reports["fidelity_audit_report"]).exists())
            self.assertTrue(Path(reports["preview_sync_report"]).exists())
            self.assertTrue(Path(reports["preview_smoke_report"]).exists())

    def test_post_jobs_failure_surfaces_failed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_path = workspace / "broken.xml"
            xml_path.write_text(
                "<Screen id='Broken'><Transaction id='tx1' serviceid='SVC_TX1' method='POST' /></Screen>",
                encoding="utf-8",
            )

            status_code, payload = _http_json(
                base_url=self.base_url,
                method="POST",
                path="/jobs",
                payload={
                    "xml_path": str(xml_path),
                    "out_dir": str(workspace / "out-e2e"),
                    "api_out_dir": str(workspace / "generated-api"),
                    "ui_out_dir": str(workspace / "generated-ui"),
                    "pretty": True,
                    "use_isolated_preview_host": True,
                },
            )
            self.assertEqual(status_code, 202)
            job_id = payload["job"]["id"]

            completed = self._wait_terminal(job_id)
            self.assertEqual(completed["status"], "failed")
            self.assertEqual(completed["result"]["exit_code"], 2)
            self.assertEqual(completed["error"]["code"], "pipeline_failed")

            status_code, artifacts_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}/artifacts",
            )
            self.assertEqual(status_code, 200)
            artifacts = artifacts_payload["artifacts"]
            self.assertEqual(artifacts["overall_status"], "failure")
            self.assertEqual(artifacts["overall_exit_code"], 2)
            self.assertEqual(artifacts["stages"]["map_api"]["status"], "failure")

    def test_studio_orchestrator_e2e_smoke_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            out_dir = workspace / "out-studio"

            status_code, payload = _http_json(
                base_url=self.base_url,
                method="POST",
                path="/jobs",
                payload={
                    "xml_path": str(FIXTURE_XML),
                    "out_dir": str(out_dir),
                    "api_out_dir": str(out_dir / "generated" / "api"),
                    "ui_out_dir": str(out_dir / "generated" / "frontend"),
                    "preview_host_source_dir": str(ROOT / "preview-host"),
                    "use_isolated_preview_host": True,
                    "render_policy_mode": "auto",
                    "pretty": True,
                },
            )
            self.assertEqual(status_code, 202)
            created_job = payload["job"]
            self.assertEqual(created_job["request"]["render_policy_mode"], "auto")
            self.assertTrue(created_job["request"]["use_isolated_preview_host"])

            job_id = created_job["id"]
            completed = self._wait_terminal(job_id)
            self.assertEqual(completed["status"], "succeeded")
            self.assertEqual(completed["result"]["summary_overview"]["overall_status"], "success")

            status_code, log_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}/logs",
            )
            self.assertEqual(status_code, 200)
            events = [entry["event"] for entry in log_payload["logs"]]
            self.assertIn("preview_host_prepared", events)
            self.assertIn("pipeline_started", events)
            self.assertIn("job_finished", events)

            status_code, artifacts_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}/artifacts",
            )
            self.assertEqual(status_code, 200)
            artifacts = artifacts_payload["artifacts"]
            self.assertEqual(artifacts["overall_status"], "success")
            self.assertIn("reports", artifacts)
            self.assertIn("stages", artifacts)
            self.assertIn("consolidated_summary", artifacts["reports"])
            self.assertTrue(Path(artifacts["reports"]["consolidated_summary"]).exists())
            self.assertIn("preview_smoke", artifacts["stages"])

    def test_history_retry_flow_records_failed_then_successful_reexecution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_path = workspace / "retry.xml"
            retry_payload = {
                "xml_path": str(xml_path),
                "out_dir": str(workspace / "out-e2e"),
                "api_out_dir": str(workspace / "generated-api"),
                "ui_out_dir": str(workspace / "generated-ui"),
                "preview_host_dir": str(ROOT / "preview-host"),
                "use_isolated_preview_host": False,
                "pretty": True,
            }

            xml_path.write_text(
                "<Screen id='Broken'><Transaction id='tx1' serviceid='SVC_TX1' method='POST' /></Screen>",
                encoding="utf-8",
            )
            status_code, first_payload = _http_json(
                base_url=self.base_url,
                method="POST",
                path="/jobs",
                payload=retry_payload,
            )
            self.assertEqual(status_code, 202)
            first_job_id = first_payload["job"]["id"]
            first_terminal = self._wait_terminal(first_job_id)
            self.assertEqual(first_terminal["status"], "failed")

            xml_path.write_text(FIXTURE_XML.read_text(encoding="utf-8"), encoding="utf-8")
            status_code, second_payload = _http_json(
                base_url=self.base_url,
                method="POST",
                path="/jobs",
                payload=retry_payload,
            )
            self.assertEqual(status_code, 202)
            second_job_id = second_payload["job"]["id"]
            second_terminal = self._wait_terminal(second_job_id)
            self.assertEqual(second_terminal["status"], "succeeded")

            status_code, history_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path="/jobs?limit=10",
            )
            self.assertEqual(status_code, 200)
            self.assertGreaterEqual(history_payload["total"], 2)

            seen = {entry["id"]: entry for entry in history_payload["jobs"]}
            self.assertIn(first_job_id, seen)
            self.assertIn(second_job_id, seen)
            self.assertEqual(seen[first_job_id]["status"], "failed")
            self.assertEqual(seen[second_job_id]["status"], "succeeded")
            self.assertEqual(
                seen[first_job_id]["request"]["xml_path"],
                seen[second_job_id]["request"]["xml_path"],
            )

    def test_post_jobs_cancel_marks_running_job_as_canceled(self) -> None:
        release = threading.Event()

        def _blocking_run(args: object) -> int:
            release.wait(timeout=10)
            return _write_success_summary(args)

        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            with mock.patch.object(orchestrator_api_module, "run_migrate_e2e", side_effect=_blocking_run):
                status_code, payload = _http_json(
                    base_url=self.base_url,
                    method="POST",
                    path="/jobs",
                    payload={
                        "xml_path": str(FIXTURE_XML),
                        "out_dir": str(workspace / "out-e2e"),
                        "api_out_dir": str(workspace / "generated-api"),
                        "ui_out_dir": str(workspace / "generated-ui"),
                        "preview_host_dir": str(ROOT / "preview-host"),
                        "use_isolated_preview_host": False,
                    },
                )
                self.assertEqual(status_code, 202)
                job_id = payload["job"]["id"]

                running_job = self._wait_status(job_id, expected_status="running")
                self.assertFalse(running_job["cancel_requested"])

                status_code, cancel_payload = _http_json(
                    base_url=self.base_url,
                    method="POST",
                    path=f"/jobs/{job_id}/cancel",
                )
                self.assertEqual(status_code, 202)
                self.assertTrue(cancel_payload["job"]["cancel_requested"])

                release.set()
                completed = self._wait_terminal(job_id)
                self.assertEqual(completed["status"], "canceled")
                self.assertEqual(completed["error"]["code"], "job_canceled")

                status_code, log_payload = _http_json(
                    base_url=self.base_url,
                    method="GET",
                    path=f"/jobs/{job_id}/logs",
                )
                self.assertEqual(status_code, 200)
                events = [entry["event"] for entry in log_payload["logs"]]
                self.assertIn("cancel_requested", events)
                self.assertIn("job_canceled", events)

    def test_get_jobs_supports_limit_and_status_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            created_job_ids: list[str] = []

            with mock.patch.object(orchestrator_api_module, "run_migrate_e2e", side_effect=_write_success_summary):
                for index in range(2):
                    job_root = workspace / f"job-{index}"
                    status_code, payload = _http_json(
                        base_url=self.base_url,
                        method="POST",
                        path="/jobs",
                        payload={
                            "xml_path": str(FIXTURE_XML),
                            "out_dir": str(job_root / "out-e2e"),
                            "api_out_dir": str(job_root / "generated-api"),
                            "ui_out_dir": str(job_root / "generated-ui"),
                            "preview_host_dir": str(ROOT / "preview-host"),
                            "use_isolated_preview_host": False,
                        },
                    )
                    self.assertEqual(status_code, 202)
                    job_id = payload["job"]["id"]
                    created_job_ids.append(job_id)
                    completed = self._wait_terminal(job_id)
                    self.assertEqual(completed["status"], "succeeded")

            status_code, limited_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path="/jobs?limit=1",
            )
            self.assertEqual(status_code, 200)
            self.assertEqual(limited_payload["limit"], 1)
            self.assertEqual(limited_payload["total"], 2)
            self.assertEqual(len(limited_payload["jobs"]), 1)
            self.assertEqual(limited_payload["jobs"][0]["id"], created_job_ids[-1])

            status_code, succeeded_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path="/jobs?status=succeeded",
            )
            self.assertEqual(status_code, 200)
            self.assertEqual(succeeded_payload["status_filter"], ["succeeded"])
            self.assertEqual(succeeded_payload["total"], 2)
            self.assertEqual(len(succeeded_payload["jobs"]), 2)
            self.assertTrue(all(job["status"] == "succeeded" for job in succeeded_payload["jobs"]))

            status_code, invalid_status_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path="/jobs?status=invalid",
            )
            self.assertEqual(status_code, 400)
            self.assertEqual(invalid_status_payload["error"]["code"], "validation_error")

            status_code, invalid_limit_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path="/jobs?limit=0",
            )
            self.assertEqual(status_code, 400)
            self.assertEqual(invalid_limit_payload["error"]["code"], "validation_error")

    def test_job_history_is_available_after_server_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            with mock.patch.object(orchestrator_api_module, "run_migrate_e2e", side_effect=_write_success_summary):
                status_code, payload = _http_json(
                    base_url=self.base_url,
                    method="POST",
                    path="/jobs",
                    payload={
                        "xml_path": str(FIXTURE_XML),
                        "out_dir": str(workspace / "out-e2e"),
                        "api_out_dir": str(workspace / "generated-api"),
                        "ui_out_dir": str(workspace / "generated-ui"),
                        "preview_host_dir": str(ROOT / "preview-host"),
                        "use_isolated_preview_host": False,
                    },
                )
                self.assertEqual(status_code, 202)
                job_id = payload["job"]["id"]
                completed = self._wait_terminal(job_id)
                self.assertEqual(completed["status"], "succeeded")

            self._restart_server()

            status_code, job_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path=f"/jobs/{job_id}",
            )
            self.assertEqual(status_code, 200)
            self.assertEqual(job_payload["job"]["id"], job_id)
            self.assertEqual(job_payload["job"]["status"], "succeeded")

            status_code, list_payload = _http_json(
                base_url=self.base_url,
                method="GET",
                path="/jobs?status=succeeded&limit=10",
            )
            self.assertEqual(status_code, 200)
            self.assertTrue(any(job["id"] == job_id for job in list_payload["jobs"]))

    def test_structured_error_responses(self) -> None:
        status_code, missing_xml_payload = _http_json(
            base_url=self.base_url,
            method="POST",
            path="/jobs",
            payload={},
        )
        self.assertEqual(status_code, 400)
        self.assertEqual(missing_xml_payload["error"]["code"], "validation_error")

        status_code, invalid_payload = _http_json(
            base_url=self.base_url,
            method="POST",
            path="/jobs",
            payload=[],
        )
        self.assertEqual(status_code, 400)
        self.assertEqual(invalid_payload["error"]["code"], "invalid_payload")

        status_code, job_not_found_payload = _http_json(
            base_url=self.base_url,
            method="GET",
            path="/jobs/does-not-exist",
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(job_not_found_payload["error"]["code"], "job_not_found")

        status_code, cancel_not_found_payload = _http_json(
            base_url=self.base_url,
            method="POST",
            path="/jobs/does-not-exist/cancel",
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(cancel_not_found_payload["error"]["code"], "job_not_found")


if __name__ == "__main__":
    unittest.main()
