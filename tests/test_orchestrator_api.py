from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.orchestrator_api import create_orchestrator_http_server  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_XML = FIXTURES_DIR / "simple_screen_fixture.txt"
KNOWN_TAGS = FIXTURES_DIR / "known_tags_all.txt"
KNOWN_ATTRS = FIXTURES_DIR / "known_attrs_all.json"


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
        self.server = create_orchestrator_http_server(
            host="127.0.0.1",
            port=0,
            workspace_root=ROOT,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

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


if __name__ == "__main__":
    unittest.main()
